"""The sandbox login for the supervisor view.

This is a simplistic authentication for demonstration purposes only, with a fixed shared
credential and no rate limiting or lockout, and it must be replaced with proper authentication
(per-user credentials or single sign-on, a supervisor role that the deployment checks, session
expiry and audit) before any production deployment.

The credential is one constant below. The login is off whenever ``SOCAREGUARD_SUPERVISOR_KEYS``
or ``SOCAREGUARD_API_KEYS`` is set: a keyed deployment signs a supervisor in with a supervisor key
instead. A sandbox sign-in is recorded in the ledger as ``admin (sandbox login)``, and the ledger
marks that actor as typed in, not checked.

A sign-in sets an HTTP-only cookie that names an entry in this process's memory. Every visitor who
types the shared credential is the same supervisor, so the view that the login opens is limited
(see ``socareguard.proxy.app``): it lists every session's action rows, but it opens another
browser's session with stand-ins only.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

PRODUCTION_WARNING = (
    "This is a simplistic authentication for demonstration purposes only, with a fixed shared "
    "credential and no rate limiting or lockout, and it must be replaced with proper "
    "authentication (per-user credentials or single sign-on, a supervisor role that the "
    "deployment checks, session expiry and audit) before any production deployment."
)

# The fixed sandbox credential (user name, password), stated in the README as sandbox-only.
DEMO_CREDENTIAL = ("admin", "demo1234")
DEMO_ACTOR = "admin (sandbox login)"
COOKIE = "socareguard_supervisor"
_MAX_LOGINS = 1000
_LIFETIME_S = 12 * 3600


def credential_ok(username: str, password: str) -> bool:
    """True when the pair is the sandbox credential."""
    user_ok = hmac.compare_digest((username or "").encode(), DEMO_CREDENTIAL[0].encode())
    pass_ok = hmac.compare_digest((password or "").encode(), DEMO_CREDENTIAL[1].encode())
    return user_ok and pass_ok


class Logins:
    """Signed-in supervisors, keyed by the SHA-256 of the cookie value, in process memory."""

    def __init__(self) -> None:
        self.entries: dict[str, tuple[str, bool, float]] = {}
        self.lock = threading.Lock()

    def start(self, actor: str, attested: bool) -> str:
        token = secrets.token_urlsafe(24)
        now = time.time()
        with self.lock:
            for k in [k for k, v in self.entries.items() if v[2] <= now]:
                del self.entries[k]
            while len(self.entries) >= _MAX_LOGINS:
                del self.entries[next(iter(self.entries))]
            self.entries[hashlib.sha256(token.encode()).hexdigest()] = (
                actor,
                attested,
                now + _LIFETIME_S,
            )
        return token

    def get(self, token: str | None) -> tuple[str, bool] | None:
        if not token:
            return None
        with self.lock:
            entry = self.entries.get(hashlib.sha256(token.encode()).hexdigest())
        if not entry or entry[2] <= time.time():
            return None
        return entry[0], entry[1]

    def end(self, token: str | None) -> None:
        if token:
            with self.lock:
                self.entries.pop(hashlib.sha256(token.encode()).hexdigest(), None)
