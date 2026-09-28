"""Session index kept in the vault's SQLite file, so a restart does not end open sessions.

The proxy answers ``GET /v1/sessions/{id}``, the panel's identity map, an override and a
supervisor release from the session's last guarded result. Those results used to live only in
process memory, so a deploy or a crash closed every session while the vault and the ledger
survived. This module adds one table, ``session_index``, beside the vault's ``mappings`` table.

What is in clear: the session id, the SHA-256 of the session token, the pack, whether the draft
was withheld, the labels of the flags raised (the ledger row already carries them), and the
times. What is encrypted under the vault key (AES-256-GCM, as the mappings are): the rest of the
result, which holds the re-identified draft, the replacement table with the originals, the event
stream and the token itself, so that a later request in the same session returns the same token.
The table is only added: the vault's own table is not changed.

A second table, ``review_tokens``, holds the read-only review links that a supervisor opens from
the supervisor view: the SHA-256 of each token, its session, who opened it and when it expires
(30 minutes after issue). The token itself is returned once and never stored.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from collections import OrderedDict
from typing import Any

from socareguard.outbound.vault import Vault
from socareguard.proxy.core import GuardedResult
from socareguard.scenarios.events import Flag

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS session_index (session TEXT PRIMARY KEY, token_sha256 TEXT, "
    "pack TEXT, withheld INTEGER, flags TEXT, created REAL, updated REAL, nonce BLOB, "
    "result_enc BLOB)"
)

_REVIEW_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS review_tokens (token_sha256 TEXT PRIMARY KEY, session TEXT, "
    "actor TEXT, attested INTEGER, issued REAL, expires REAL)"
)
REVIEW_TTL_S = 30 * 60


def _now() -> float:
    """The clock the review tokens use (a test moves it forward to expire a token)."""
    return time.time()


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class _Event(dict):
    """An event restored from the index. The app only reads events through ``model_dump``."""

    def model_dump(self) -> dict[str, Any]:
        return dict(self)

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e


def _dump(res: GuardedResult, token: str) -> dict[str, Any]:
    return {
        "token": token,
        "reply": res.reply,
        "reply_withheld": res.reply_withheld,
        "decision": res.decision,
        "withheld": res.withheld,
        "flags": [f.model_dump() for f in res.flags],
        "flags_withheld": [f.model_dump() for f in res.flags_withheld],
        "events": [e.model_dump() for e in res.events],
        "replacements": res.replacements,
        "recipients": res.recipients,
        "ledger_row": res.ledger_row,
        "usage": res.usage,
    }


def _load(session: str, d: dict[str, Any]) -> GuardedResult:
    return GuardedResult(
        session=session,
        outbound_messages=[],
        reply_raw="",
        reply=d["reply"],
        events=[_Event(e) for e in d["events"]],
        flags=[Flag.model_validate(f) for f in d["flags"]],
        decision=d["decision"],
        ledger_row=d["ledger_row"],
        usage=d.get("usage") or {},
        replacements=d["replacements"],
        withheld=d["withheld"],
        reply_withheld=d["reply_withheld"],
        flags_withheld=[Flag.model_validate(f) for f in d["flags_withheld"]],
        recipients=d.get("recipients") or [],
    )


class SessionStore:
    """The session index: an in-memory cache in front of the ``session_index`` table."""

    def __init__(self, vault: Vault, max_sessions: int = 500):
        self.vault = vault
        self.max_sessions = max_sessions
        self.cache: OrderedDict[str, tuple[GuardedResult, str]] = OrderedDict()
        with vault.lock:
            vault.db.execute(_SCHEMA)
            vault.db.execute(_REVIEW_SCHEMA)
            vault.db.commit()

    # ---------- reads ----------
    def _row(self, session: str) -> tuple[GuardedResult, str] | None:
        if session in self.cache:
            self.cache.move_to_end(session)
            return self.cache[session]
        with self.vault.lock:
            row = self.vault.db.execute(
                "SELECT nonce, result_enc FROM session_index WHERE session=?", (session,)
            ).fetchone()
            if not row:
                return None
            d = json.loads(self.vault._dec(row[0], row[1]))
        entry = (_load(session, d), d["token"])
        self._cache(session, entry)
        return entry

    def get(self, session: str) -> GuardedResult | None:
        entry = self._row(session)
        return entry[0] if entry else None

    def token(self, session: str) -> str | None:
        entry = self._row(session)
        return entry[1] if entry else None

    def token_ok(self, session: str, token: str) -> bool:
        with self.vault.lock:
            row = self.vault.db.execute(
                "SELECT token_sha256 FROM session_index WHERE session=?", (session,)
            ).fetchone()
        return bool(row) and hmac.compare_digest(row[0], _sha(token))

    def __contains__(self, session: str) -> bool:
        if session in self.cache:
            return True
        with self.vault.lock:
            return bool(
                self.vault.db.execute(
                    "SELECT 1 FROM session_index WHERE session=?", (session,)
                ).fetchone()
            )

    def pack(self, session: str) -> str | None:
        """The session's pack, from the clear column."""
        with self.vault.lock:
            row = self.vault.db.execute(
                "SELECT pack FROM session_index WHERE session=?", (session,)
            ).fetchone()
        return row[0] if row else None

    def withheld_sessions(self) -> list[dict[str, Any]]:
        """Sessions whose latest result withheld the draft, newest first, read from the clear
        columns only (nothing is decrypted), with the number of review links still open."""
        now = _now()
        with self.vault.lock:
            rows = self.vault.db.execute(
                "SELECT session, pack, flags, created, updated FROM session_index "
                "WHERE withheld=1 ORDER BY updated DESC"
            ).fetchall()
            open_reviews = dict(
                self.vault.db.execute(
                    "SELECT session, COUNT(*) FROM review_tokens WHERE expires > ? "
                    "GROUP BY session",
                    (now,),
                ).fetchall()
            )
        return [
            {
                "session": r[0],
                "pack": r[1],
                "flags": json.loads(r[2] or "[]"),
                "created": r[3],
                "updated": r[4],
                "reviews_open": open_reviews.get(r[0], 0),
            }
            for r in rows
        ]

    def issue_review_token(
        self, session: str, actor: str, attested: bool, ttl: float = REVIEW_TTL_S
    ) -> tuple[str, float]:
        """A read-only review token for one session. Only its hash is stored. Returns the token
        and its expiry time. Expired tokens are removed here."""
        token = secrets.token_urlsafe(24)
        now = _now()
        with self.vault.lock:
            self.vault.db.execute("DELETE FROM review_tokens WHERE expires <= ?", (now,))
            self.vault.db.execute(
                "INSERT INTO review_tokens VALUES (?,?,?,?,?,?)",
                (_sha(token), session, actor, int(bool(attested)), now, now + ttl),
            )
            self.vault.db.commit()
        return token, now + ttl

    def review_token_ok(self, session: str, token: str) -> bool:
        """True when ``token`` is an unexpired review token for ``session``."""
        if not token:
            return False
        with self.vault.lock:
            row = self.vault.db.execute(
                "SELECT session, expires FROM review_tokens WHERE token_sha256=?", (_sha(token),)
            ).fetchone()
        return bool(row) and hmac.compare_digest(row[0], session) and row[1] > _now()

    def older_than(self, cutoff: float) -> list[str]:
        with self.vault.lock:
            return [
                r[0]
                for r in self.vault.db.execute(
                    "SELECT session FROM session_index WHERE updated < ?", (cutoff,)
                )
            ]

    # ---------- writes ----------
    def _cache(self, session: str, entry: tuple[GuardedResult, str]) -> None:
        self.cache[session] = entry
        self.cache.move_to_end(session)
        while len(self.cache) > max(self.max_sessions, 1):
            self.cache.popitem(last=False)

    def put(self, session: str, res: GuardedResult, token: str, pack: str) -> list[str]:
        """Store the session's latest result. Returns the sessions evicted to stay within
        ``max_sessions`` (oldest first); the caller forgets their vault mappings."""
        now = time.time()
        blob = json.dumps(_dump(res, token), ensure_ascii=False)
        flags = sorted({f.label for f in res.flags} | {f.label for f in res.flags_withheld})
        with self.vault.lock:
            nonce, enc = self.vault._enc(blob)
            created = self.vault.db.execute(
                "SELECT created FROM session_index WHERE session=?", (session,)
            ).fetchone()
            self.vault.db.execute(
                "INSERT OR REPLACE INTO session_index VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    session,
                    _sha(token),
                    pack,
                    int(bool(res.withheld)),
                    json.dumps(flags),
                    created[0] if created else now,
                    now,
                    nonce,
                    enc,
                ),
            )
            evicted: list[str] = []
            n = self.vault.db.execute("SELECT COUNT(*) FROM session_index").fetchone()[0]
            if n > self.max_sessions > 0:
                evicted = [
                    r[0]
                    for r in self.vault.db.execute(
                        "SELECT session FROM session_index ORDER BY updated ASC LIMIT ?",
                        (n - self.max_sessions,),
                    )
                ]
                self.vault.db.executemany(
                    "DELETE FROM session_index WHERE session=?", [(s,) for s in evicted]
                )
                self.vault.db.executemany(
                    "DELETE FROM review_tokens WHERE session=?", [(s,) for s in evicted]
                )
            self.vault.db.commit()
        self._cache(session, (res, token))
        for s in evicted:
            self.cache.pop(s, None)
        return evicted

    def pop(self, session: str) -> None:
        self.cache.pop(session, None)
        with self.vault.lock:
            self.vault.db.execute("DELETE FROM session_index WHERE session=?", (session,))
            self.vault.db.execute("DELETE FROM review_tokens WHERE session=?", (session,))
            self.vault.db.commit()
