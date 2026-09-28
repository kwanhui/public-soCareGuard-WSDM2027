"""Encrypted local vault for the surrogate mapping.

Originals are stored AES-256-GCM encrypted under a master key that never leaves the
premises. Surrogates are stored in clear because the inbound side looks them up in the
model's reply. The mapping is per session and is never exported. The vault is the
component PDPC's Guide to Basic Anonymisation calls the identity mapping table, and the
requirement that it be kept apart from the pseudonymised payload is met by construction:
only the payload crosses the boundary.
"""

from __future__ import annotations

import base64
import binascii
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULT_PATH = Path(os.environ.get("SOCAREGUARD_VAULT", "vault/socareguard.sqlite"))
KEY_ENV = "SOCAREGUARD_VAULT_KEY"


def _decode_key(text: str, source: str) -> bytes:
    """A 256-bit key written as base64 (the key file's own format)."""
    try:
        key = base64.b64decode(text.strip(), validate=True)
    except (ValueError, binascii.Error):
        key = b""
    if len(key) != 32:
        raise RuntimeError(
            f"{source} is not a 256-bit key in base64 (44 characters ending in '='). Set "
            f"{KEY_ENV} to the path of a key file or to the key itself."
        )
    return key


def _env_key(value: str) -> bytes:
    """``SOCAREGUARD_VAULT_KEY`` holds either the path to a key file or the key itself (base64).
    A value that names an existing file is read as a key file; a value that looks like a path
    (it contains a slash and does not decode as a key) but names no file is an error, so a
    mistyped mount point never silently becomes a key."""
    candidate = Path(value).expanduser()
    if candidate.is_file():
        return _decode_key(candidate.read_text(), f"key file {candidate}")
    try:
        return _decode_key(value, KEY_ENV)
    except RuntimeError:
        if "/" in value or value.endswith(".key"):
            raise RuntimeError(
                f"{KEY_ENV} names {value}, which is not a file, and is not a base64 key either"
            ) from None
        raise


def _master_key(path: Path) -> bytes:
    """Read the key from ``SOCAREGUARD_VAULT_KEY`` (a key file's path, or the key in base64) or
    from ``<vault>.key``, created with mode 600 when neither exists."""
    if os.environ.get(KEY_ENV):
        return _env_key(os.environ[KEY_ENV])
    key_file = path.with_suffix(".key")
    if key_file.exists():
        return _decode_key(key_file.read_text(), f"key file {key_file}")
    if (
        path.exists()
        and path.stat().st_size > 0
        and not os.environ.get("SOCAREGUARD_VAULT_NEW_KEY")
    ):
        raise RuntimeError(
            f"{path} exists but its key file {key_file} is missing: refusing to mint a new key "
            "over an existing vault (the old mappings would become unreadable). Restore the key, "
            f"set {KEY_ENV}, or set SOCAREGUARD_VAULT_NEW_KEY=1 to start a fresh vault knowingly."
        )
    key = AESGCM.generate_key(bit_length=256)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.touch(mode=0o600)
    key_file.write_text(base64.b64encode(key).decode())
    return key


@dataclass(frozen=True)
class Mapping:
    session: str
    original: str
    surrogate: str
    category: str
    kind: str  # "surrogate" or "generalised"
    entity_id: str


class Vault:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.key = _master_key(self.path)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.Lock()
        # One row per (entity, surrogate): a full name and its short form are two entities that
        # may share a surrogate, and two originals may share one generalised phrase. Restoration
        # decides what to do with the duplicates; the vault keeps them all.
        old = self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='mappings'"
        ).fetchone()
        if old and "PRIMARY KEY (session, surrogate)" in old[0]:
            self.db.execute("ALTER TABLE mappings RENAME TO mappings_v1")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS mappings (session TEXT, entity_id TEXT, category TEXT, kind TEXT, "
            "surrogate TEXT, nonce BLOB, original_enc BLOB, created REAL, "
            "PRIMARY KEY (session, entity_id, surrogate))"
        )
        if old and "PRIMARY KEY (session, surrogate)" in old[0]:
            self.db.execute("INSERT OR IGNORE INTO mappings SELECT * FROM mappings_v1")
            self.db.execute("DROP TABLE mappings_v1")
        self.db.commit()

    def _enc(self, text: str) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        return nonce, AESGCM(self.key).encrypt(nonce, text.encode(), None)

    def _dec(self, nonce: bytes, blob: bytes) -> str:
        return AESGCM(self.key).decrypt(nonce, blob, None).decode()

    def put(self, m: Mapping) -> None:
        with self.lock:
            nonce, enc = self._enc(m.original)
            self.db.execute(
                "INSERT OR REPLACE INTO mappings VALUES (?,?,?,?,?,?,?,?)",
                (m.session, m.entity_id, m.category, m.kind, m.surrogate, nonce, enc, time.time()),
            )
            self.db.commit()

    def mappings(self, session: str) -> list[Mapping]:
        with self.lock:
            rows = self.db.execute(
                "SELECT entity_id, category, kind, surrogate, nonce, original_enc FROM mappings WHERE session=?",
                (session,),
            ).fetchall()
            return [Mapping(session, self._dec(n, e), s, c, k, eid) for eid, c, k, s, n, e in rows]

    def surrogates(self, session: str) -> set[str]:
        with self.lock:
            return {
                r[0]
                for r in self.db.execute(
                    "SELECT surrogate FROM mappings WHERE session=?", (session,)
                )
            }

    def purge_older_than(self, seconds: float) -> int:
        """Retention sweep: drop every mapping created more than ``seconds`` ago."""
        with self.lock:
            cur = self.db.execute(
                "DELETE FROM mappings WHERE created < ?", (time.time() - seconds,)
            )
            self.db.commit()
            return cur.rowcount

    def forget(self, session: str) -> int:
        with self.lock:
            cur = self.db.execute("DELETE FROM mappings WHERE session=?", (session,))
            self.db.commit()
            return cur.rowcount

    def close(self) -> None:
        self.db.close()
