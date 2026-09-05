"""Encrypted local vault for the surrogate mapping.

Originals are stored AES-256-GCM encrypted under a master key that never leaves the
premises; surrogates are stored in clear because the inbound side looks them up in the
model's reply. The mapping is per session and is never exported. The vault is the
component PDPC's Guide to Basic Anonymisation calls the identity mapping table, and the
requirement that it be kept apart from the pseudonymised payload is met by construction:
only the payload crosses the boundary.
"""

from __future__ import annotations

import base64
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULT_PATH = Path(os.environ.get("SOCAREGUARD_VAULT", "vault/socareguard.sqlite"))
KEY_ENV = "SOCAREGUARD_VAULT_KEY"


def _master_key(path: Path) -> bytes:
    """Read the key from the environment (base64) or from ``<vault>.key`` created with mode 600."""
    if os.environ.get(KEY_ENV):
        return base64.b64decode(os.environ[KEY_ENV])
    key_file = path.with_suffix(".key")
    if key_file.exists():
        return base64.b64decode(key_file.read_text().strip())
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
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS mappings (session TEXT, entity_id TEXT, category TEXT, kind TEXT, "
            "surrogate TEXT, nonce BLOB, original_enc BLOB, created REAL, PRIMARY KEY (session, surrogate))"
        )
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

    def forget(self, session: str) -> int:
        with self.lock:
            cur = self.db.execute("DELETE FROM mappings WHERE session=?", (session,))
            self.db.commit()
            return cur.rowcount

    def close(self) -> None:
        self.db.close()
