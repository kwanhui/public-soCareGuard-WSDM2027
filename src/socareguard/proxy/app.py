"""FastAPI app exposing an OpenAI-compatible ``/v1/chat/completions``.

Headers: ``X-SoCareGuard-Pack`` (disability | domestic-violence | youth-offending; falls back to
``SOCAREGUARD_DEFAULT_PACK`` and says so in the response), optional ``X-SoCareGuard-Session``
and ``X-SoCareGuard-Actor`` (the staff identity the ledger records). When ``SOCAREGUARD_API_KEYS``
is set, every ``/v1`` route requires ``Authorization: Bearer <key>``. The response is the
standard chat completion object plus a ``socareguard`` field carrying the event stream, flags,
recipients and the ledger row, which the transparency panel renders.

``GET /supervisor`` is the supervisor view: the ledger chain check, the withheld drafts that wait
for a release, and one period of escalations, releases, overrides, accepted rewrites and opened
reviews. With ``SOCAREGUARD_SUPERVISOR_KEYS`` set it needs a supervisor key. Without keys it
offers the sandbox login of ``socareguard.proxy.demo_login``, which is for demonstration only.
Under that shared login, the review page opens the pseudonymised columns only (what left, what
came back, the flags and the ledger rows), since it sends the review token without the session's
own token.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from socareguard.detect import sg as sg_recognisers
from socareguard.policy.loader import PACK_DIR, available_packs, load_pack
from socareguard.proxy import demo_login
from socareguard.proxy.core import Guard
from socareguard.proxy.sessions import REVIEW_TTL_S, SessionStore
from socareguard.proxy.supervisor import (
    KIND_PLURAL,
    KIND_SINGULAR,
    build_summary,
    chip_groups,
    parse_when,
)
from socareguard.taxonomy import BY_ID

DEFAULT_MODEL = os.environ.get("SOCAREGUARD_DEFAULT_MODEL", "openai/gpt-4.1-mini")
ALLOWED_MODELS = set(
    os.environ.get("SOCAREGUARD_MODELS", "openai/gpt-4.1-mini,anthropic/claude-sonnet-5").split(",")
)
DEFAULT_PACK = os.environ.get("SOCAREGUARD_DEFAULT_PACK", "domestic-violence")
API_KEYS = {k.strip() for k in os.environ.get("SOCAREGUARD_API_KEYS", "").split(",") if k.strip()}
SUPERVISOR_KEYS = {
    k.strip() for k in os.environ.get("SOCAREGUARD_SUPERVISOR_KEYS", "").split(",") if k.strip()
}

SANDBOX = os.environ.get("SOCAREGUARD_SANDBOX", "0") == "1"
# honour X-Forwarded-For, X-Forwarded-Proto and X-Forwarded-Host (only behind a proxy you control)
TRUST_PROXY = os.environ.get("SOCAREGUARD_TRUST_PROXY", "0") == "1"
# The supervisor cookie. With Secure on (https, forwarded https, or SOCAREGUARD_COOKIE_SECURE=1)
# it is SameSite=None and Partitioned, so the sign-in holds when the app is shown in another
# site's frame (the Hugging Face Space page frames the app from hf.space). Over plain http
# (local runs) it is SameSite=Lax without Secure. "1" forces Secure on, "0" off, "auto" decides.
COOKIE_SECURE = os.environ.get("SOCAREGUARD_COOKIE_SECURE", "auto").strip().lower()
# Origins, besides the app's own, from which a cookie-authenticated request that changes state is
# accepted (comma-separated, e.g. https://agency.example). The app's own origin needs no entry.
ALLOWED_ORIGINS = {
    o.strip().rstrip("/").lower()
    for o in os.environ.get("SOCAREGUARD_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
}
RETENTION_HOURS = float(
    os.environ.get("SOCAREGUARD_RETENTION_HOURS", "24" if SANDBOX else "0")
)  # 0 = keep until purged by DELETE /v1/sessions/{id}
MAX_PER_HOUR = int(os.environ.get("SOCAREGUARD_MAX_REQUESTS_PER_HOUR", "0"))  # 0 = unlimited
MAX_SESSIONS = int(os.environ.get("SOCAREGUARD_MAX_SESSIONS", "500"))
BAD_JSON = "the request body is not valid JSON"
_HERE = Path(__file__).resolve().parent
# Per-category precision of the conduct screen on the labelled synthetic drafts (results-v1.3),
# shown on each flag card beside the judge's own confidence. Derived from
# docs/metrics/screen-v1.3-v1.1-drafts.json (per-label precision at the reported 0.5 threshold).
# The v1.1 and v1.2 tables (screen_precision_v1_1.json, screen_precision_v1_2.json) are kept in
# place for the record. The v1.2 and v1.3 values are equal.
_PRECISION_FILE = _HERE / "screen_precision_v1_3.json"
SCREEN_PRECISION = json.loads(_PRECISION_FILE.read_text()) if _PRECISION_FILE.exists() else {}

# Every ledger append logs "ledger head <sha> rows <n>" here. Shipping the server log off the
# host anchors the chain outside it (see socareguard.ledger).
_anchor_log = logging.getLogger("socareguard.ledger")
_anchor_log.setLevel(logging.INFO)
if not _anchor_log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    _anchor_log.addHandler(_h)
# A request that fails inside the pipeline is logged here at ERROR with its traceback and a
# short error id; the 503 body carries the same id, so an operator can find the cause.
_error_log = logging.getLogger("socareguard.proxy")
if not _error_log.handlers:
    _eh = logging.StreamHandler()
    _eh.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    _error_log.addHandler(_eh)
_SCENARIO_DIR = Path(os.environ.get("SOCAREGUARD_SCENARIOS", "demo/sample-inputs/scenarios"))


def load_scenarios() -> list[dict[str, Any]]:
    out = []
    for f in sorted(_SCENARIO_DIR.glob("uc*.jsonl")) if _SCENARIO_DIR.exists() else []:
        head, turn = None, None
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("kind") == "scenario":
                head = d
            elif d.get("kind") == "user_turn" and turn is None:
                turn = d
        if head and turn:
            out.append(
                {
                    "id": head["id"],
                    "pack": head["pack"],
                    "use_case": head["use_case"],
                    "title": head["title"],
                    "short": head["title"].split(":")[0].split(",")[0].strip(),
                    "summary": head.get("summary", ""),
                    "instruction": turn["instruction"],
                    "note": turn["note"],
                    "compare_instruction": head.get("compare_instruction"),
                    "has_recording": any(
                        json.loads(x).get("kind") == "receive"
                        for x in f.read_text().splitlines()
                        if x.strip()
                    ),
                    "recordings": _recording_labels(head["id"]),
                    "recorded_screen": head.get("recorded_screen"),
                }
            )
    # The recipient check (the audience gate): one note, two recipients. Built on the disability scenario so the
    # reviewer sees the same text screened for the case file and for an employer.
    uc1 = next((s for s in out if s["id"] == "uc1-youth-offending"), None)
    if uc1 is not None:
        out.append(
            {
                "id": "escalation",
                "pack": uc1["pack"],
                "use_case": 6,
                "title": "Escalation: a protected young person named to an external recipient",
                "short": "Escalation",
                "summary": (
                    "The probation intake note is drafted as an email to the school principal. "
                    "Naming a young person under the Children and Young Persons Act alongside the "
                    "offence to a recipient outside the agency escalates (I14): the draft is withheld "
                    "from this screen and only a supervisor can release it, with a reason that goes "
                    "into the record."
                ),
                "instruction": (
                    "Write an email to the school principal explaining Amirul's court case and "
                    "probation conditions so the school can manage him."
                ),
                "note": uc1["note"],
                "compare_instruction": None,
                "has_recording": (_SCENARIO_DIR / "escalation.jsonl").exists(),
                "recordings": _recording_labels("escalation"),
                "recorded_screen": None,
            }
        )
    uc3 = next((s for s in out if s["id"] == "uc3-disability"), None)
    if uc3 is not None:
        out.append(
            {
                "id": "audience-gate",
                "pack": uc3["pack"],
                "use_case": 5,
                "title": "Recipient check: the same note for the case file and for an employer",
                "short": "Recipient check",
                "summary": (
                    "The same care-plan note is drafted twice: once as a summary for the "
                    "practitioner's own case record, once as an introduction to a cafe supervisor. "
                    "Disclosure flags apply only to the recipient outside the agency."
                ),
                "instruction": uc3["instruction"],
                "note": uc3["note"],
                "compare_instruction": (
                    "Summarise this care plan update for my own case record and list the next steps."
                ),
                "has_recording": False,
                "recordings": [],
                "recorded_screen": None,
            }
        )
    return out


class RateLimiter:
    def __init__(self, per_hour: int):
        self.per_hour = per_hour
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.per_hour <= 0:
            return True
        now = time.time()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 3600:
                q.popleft()
            if len(q) >= self.per_hour:
                return False
            q.append(now)
            return True


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[dict[str, Any]]
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    replay_scenario: str | None = None  # reuse a shipped scenario's recorded model reply
    replay_model: str | None = None  # which recording, when the scenario keeps one per provider


def _recordings(scenario_id: str) -> list[dict[str, Any]]:
    """The recorded model replies of a shipped scenario, in file order. Each carries the seed of
    the scenario's first turn, the provider, model and date of the recording, and the
    pseudonymised text that the model was given (the ``send`` event before the reply), when the
    script has it."""
    f = _SCENARIO_DIR / f"{scenario_id}.jsonl"
    if not f.exists() or "/" in scenario_id or "\\" in scenario_id:
        return []
    seed, last_send, out = None, None, []
    for line in f.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("kind") == "user_turn" and seed is None:
            seed = d.get("seq")
        elif d.get("kind") == "send":
            last_send = d.get("outbound_text")
        elif d.get("kind") == "receive" and d.get("text"):
            out.append(
                {
                    "seed": seed,
                    "text": d["text"],
                    "provider": d.get("provider"),
                    "model": d.get("model"),
                    "recorded_at": d.get("recorded_at"),
                    "outbound_text": last_send,
                }
            )
            last_send = None
    return out


def _fixture_for(scenario_id: str, model: str | None = None) -> dict[str, Any] | None:
    """The recorded reply and seed of a shipped scenario, so the demo can replay the provider
    call deterministically. With ``model``, the recording from that model (a scenario may keep
    one per provider); otherwise the first. The guard itself still runs live."""
    recs = _recordings(scenario_id)
    if model:
        recs = [r for r in recs if r["model"] == model]
    return recs[0] if recs else None


def _recording_labels(scenario_id: str) -> list[dict[str, str]]:
    """What the panel lists for a scenario's recordings: the model and the date it was recorded."""
    return [
        {"model": r["model"] or "", "recorded_on": (r["recorded_at"] or "")[:10]}
        for r in _recordings(scenario_id)
    ]


class OverrideRequest(BaseModel):
    session: str
    pack: str
    by: str | None = None
    flag_labels: list[str]
    reason: str
    kind: str = "override"  # override | rewrite_accepted
    request_row_sha256: str | None = None
    draft_sha256: str | None = None  # hash of the text the practitioner kept or applied


DRAFT_HASH_REQUIRED = (
    "draft_sha256 is required: send the SHA-256 (64 hex characters) of the text that was kept "
    "or applied, so the ledger row can be matched against it later"
)


def _is_sha256(value: str | None) -> bool:
    return bool(value) and len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def _reason_has_identifier(reason: str) -> bool:
    """A reason is kept in the ledger as typed and never purged, so it must not carry a direct
    identifier. Uses the same Singapore recognisers as the outbound path: NRIC/FIN with its
    checksum, Singapore phone numbers, and case references."""
    return bool(
        any(h.score >= 1.0 for h in sg_recognisers.find_nric(reason))
        or sg_recognisers.find_phone(reason)
        or sg_recognisers.find_case_ref(reason)
    )


REASON_IDENTIFIER = (
    "Reason must not contain an identifier (NRIC/FIN, phone number or case reference)"
)


REASON_CAP = 300  # the judge's reason is capped at this length before it reaches the proxy


def display_reason(reason: str, cap: int = REASON_CAP) -> str:
    """The judge's reason as the flag card shows it. A reason that reaches the cap was cut, and
    a plain slice can end mid-word ("...risk, contra"), so it is cut back to the last whole word
    and ends with an ellipsis. A reason under the cap, or one ending on a full stop, is unchanged."""
    text = (reason or "").rstrip()
    if len(text) < cap - 20 or text.endswith((".", "!", "?", ".)", '."', ".\u201d")):
        return text
    if len(text) >= cap and " " in text[cap // 2 :]:
        text = text[: text.rfind(" ")]
    return text.rstrip(" ,;:-\u2013") + "\u2026"


def _flag_out(f: Any) -> dict[str, Any]:
    d = f.model_dump()
    if d.get("reason"):
        d["reason"] = display_reason(d["reason"])
    return d


def _openai_error(status: int, message: str, code: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "message": message,
                "type": "invalid_request_error" if status < 500 else "server_error",
                "code": code,
                "param": None,
            },
            "detail": message,  # kept for older clients of this proxy
        },
    )


def _client_ip(request: Request) -> str:
    direct = request.client.host if request.client else "?"
    if TRUST_PROXY and request.headers.get("x-forwarded-for"):
        return request.headers["x-forwarded-for"].split(",")[0].strip()
    return direct


def _base_url(request: Request) -> str:
    """The URL a client should use to reach this proxy. Behind a TLS-terminating reverse proxy
    the app sees plain http, so with SOCAREGUARD_TRUST_PROXY=1 the scheme and host forwarded by
    that proxy are used instead."""
    url = request.base_url
    if TRUST_PROXY:
        proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        host = request.headers.get("x-forwarded-host", "").split(",")[0].strip()
        if proto in ("http", "https"):
            url = url.replace(scheme=proto)
        if host:
            url = url.replace(netloc=host)
    return str(url).rstrip("/")


def _cookie_secure(request: Request) -> bool:
    """Whether the supervisor cookie is marked Secure. Behind the Space's proxy the app may see
    plain http, so the forwarded scheme counts as well as the configuration."""
    if COOKIE_SECURE in ("1", "true", "yes", "on"):
        return True
    if COOKIE_SECURE in ("0", "false", "no", "off"):
        return False
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return proto == "https" or request.url.scheme == "https"


def _set_supervisor_cookie(
    resp: Response, request: Request, value: str, clear: bool = False
) -> None:
    """Set (or clear) the supervisor cookie, with the same attributes both times. Secure:
    SameSite=None and Partitioned (CHIPS), so it is kept in a cross-site frame. Plain http (local
    runs): SameSite=Lax, since a browser refuses SameSite=None without Secure. Starlette sets
    Partitioned only on Python 3.14 and later, so the attribute is appended to the header here."""
    secure = _cookie_secure(request)
    resp.set_cookie(
        demo_login.COOKIE,
        value,
        max_age=0 if clear else None,
        expires=0 if clear else None,
        path="/",
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
    )
    if secure:
        name, header = next(
            (k, v)
            for k, v in reversed(resp.raw_headers)
            if k == b"set-cookie" and v.startswith(demo_login.COOKIE.encode() + b"=")
        )
        i = resp.raw_headers.index((name, header))
        resp.raw_headers[i] = (name, header + b"; Partitioned")


def _norm_origin(scheme: str, netloc: str) -> str:
    netloc = netloc.lower()
    if (scheme == "https" and netloc.endswith(":443")) or (
        scheme == "http" and netloc.endswith(":80")
    ):
        netloc = netloc.rsplit(":", 1)[0]
    return netloc


def _same_origin(request: Request) -> bool:
    """False when the request names a source (Origin, else Referer) that is neither this app's
    host (the Host or X-Forwarded-Host header) nor in SOCAREGUARD_ALLOWED_ORIGINS. With neither
    header, a browser's Sec-Fetch-Site of cross-site or same-site is refused too; a request with
    no such header at all (a script, curl, a test client) passes."""
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return request.headers.get("sec-fetch-site", "").lower() not in ("cross-site", "same-site")
    if source.strip().lower() == "null":
        return False
    parts = urlsplit(source.strip())
    scheme = parts.scheme.lower()
    if not scheme or not parts.netloc:
        return False
    if f"{scheme}://{parts.netloc.lower()}".rstrip("/") in ALLOWED_ORIGINS:
        return True
    own = {
        h.strip()
        for h in (
            request.headers.get("host", ""),
            request.headers.get("x-forwarded-host", "").split(",")[0],
        )
        if h.strip()
    }
    netloc = _norm_origin(scheme, parts.netloc)
    return any(netloc in (_norm_origin("https", h), _norm_origin("http", h)) for h in own)


def _csrf_guarded(request: Request) -> bool:
    """The requests that the origin check applies to: the sign-in and sign-out forms, and every
    request that changes state and carries the supervisor cookie without an Authorization
    header. The release of a withheld draft is a GET that writes a ledger row, so it counts."""
    path, method = request.url.path, request.method.upper()
    if method == "POST" and path in ("/supervisor/login", "/supervisor/logout"):
        return True
    if demo_login.COOKIE not in request.cookies or request.headers.get("authorization"):
        return False
    if method not in ("GET", "HEAD", "OPTIONS"):
        return True
    return path.startswith("/v1/sessions/") and path.endswith("/withheld")


def _require_key(request: Request) -> None:
    if not API_KEYS:
        return
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if token not in API_KEYS:
        raise HTTPException(401, "missing or invalid API key")


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return auth[7:].strip() if auth.lower().startswith("bearer ") else ""


def _actor(request: Request, fallback: str | None = None) -> str:
    return (
        request.headers.get("x-socareguard-actor")
        or fallback
        or ("sandbox-visitor" if SANDBOX else "unattributed")
    )


def _attested(request: Request) -> bool:
    """The actor is attested when the request carried a configured API key; otherwise the
    staff id is self-asserted and the ledger says so."""
    return bool(API_KEYS) and _bearer(request) in API_KEYS


def _keys_configured() -> bool:
    """Any key configured turns the sandbox login off."""
    return bool(API_KEYS or SUPERVISOR_KEYS)


# The event kinds a review token opens without the session's own token or a key. The detection event carries
# the typed text and is left out. The generalisation event keeps its rule ids only, and the leak
# check keeps its counts and the stand-ins the model reformatted, without the echoed originals.
_REVIEW_EVENTS = {
    "generalise",
    "substitute",
    "send",
    "receive",
    "screen",
    "reidentify",
    "leakcheck",
    "action",
    "ledger",
}


def _pseudonymise(text: str | None, pairs: list[tuple[str, str]]) -> str | None:
    """Put the stand-ins back in place of the originals, in one pass (longest original first),
    so a stand-in already put in is never replaced again. An original made of digits only (an
    age) matches only where no letter or digit borders it, so it is not replaced inside a
    stand-in NRIC. Any other original matches wherever it occurs, so none is left in the text."""
    if not text or not pairs:
        return text
    lookup = dict(pairs)

    def alt(original: str) -> str:
        if original.isdigit():
            return rf"(?<![A-Za-z0-9]){re.escape(original)}(?![A-Za-z0-9])"
        return re.escape(original)

    pattern = re.compile("|".join(alt(o) for o in sorted(lookup, key=len, reverse=True)))
    return pattern.sub(lambda m: lookup[m.group(0)], text)


def create_app(guard: Guard | None = None) -> FastAPI:
    app = FastAPI(title="SoCareGuard", version="0.2.0")
    app.state.guard = guard or Guard()
    # The session index (result, token hash, pack, withheld state, flags) lives in the vault's
    # SQLite file, so a restart keeps every open session readable and releasable.
    app.state.sessions = SessionStore(app.state.guard.vault, MAX_SESSIONS)
    app.state.limiter = RateLimiter(MAX_PER_HOUR)
    app.state.logins = demo_login.Logins()
    app.state.last_sweep = 0.0
    if RETENTION_HOURS <= 0:
        _error_log.warning(
            "retention is disabled (SOCAREGUARD_RETENTION_HOURS=0): the identity map and "
            "sessions are kept until purged by DELETE /v1/sessions/{id}"
        )

    def sweep() -> None:
        if RETENTION_HOURS <= 0 or time.time() - app.state.last_sweep < 600:
            return
        app.state.last_sweep = time.time()
        n = app.state.guard.vault.purge_older_than(RETENTION_HOURS * 3600)
        cutoff = time.time() - RETENTION_HOURS * 3600
        old = app.state.sessions.older_than(cutoff)
        for s in old:
            app.state.sessions.pop(s)
        if n or old:
            app.state.guard.ledger.append(
                {
                    "actor": "system",
                    "actor_attested": True,
                    "decision": "retention_sweep",
                    "mappings_removed": n,
                    "sessions_closed": len(old),
                    "retention_hours": RETENTION_HOURS,
                }
            )

    def authorised(session: str, request: Request) -> Any:
        """A session's map, reply and purge are reachable by the client that created it (its
        token) or by a holder of a configured API key. Session ids alone open nothing."""
        res = app.state.sessions.get(session)
        if not res:
            raise HTTPException(404, "unknown session")
        auth = request.headers.get("authorization", "")
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if API_KEYS and bearer in API_KEYS:
            return res
        token = request.headers.get("x-socareguard-session-token") or request.query_params.get(
            "token"
        )
        if not token:
            raise HTTPException(403, "Session token required")
        if not app.state.sessions.token_ok(session, token):
            raise HTTPException(403, "this session belongs to another client")
        return res

    def supervisor_identity(request: Request) -> tuple[str, bool] | None:
        """(actor, attested) for a supervisor key in the Authorization header or a signed-in
        supervisor cookie; None otherwise. A sandbox login stops counting once keys are set."""
        bearer = _bearer(request)
        if SUPERVISOR_KEYS and bearer in SUPERVISOR_KEYS:
            return request.headers.get("x-socareguard-actor") or "supervisor key", True
        login = app.state.logins.get(request.cookies.get(demo_login.COOKIE))
        if login and (login[1] or not _keys_configured()):
            return login
        return None

    def _supervisor(request: Request) -> tuple[str, bool]:
        """The supervisor gate. With keys configured, a supervisor key or a key sign-in, else 403.
        Without keys, the sandbox login, else 403."""
        who = supervisor_identity(request)
        if who is None:
            if _keys_configured():
                raise HTTPException(
                    403, "the supervisor view requires a key listed in SOCAREGUARD_SUPERVISOR_KEYS"
                )
            raise HTTPException(403, "sign in at /supervisor first")
        return who

    def review_ok(session: str, request: Request) -> bool:
        token = request.headers.get("x-socareguard-review-token") or request.query_params.get(
            "review"
        )
        return bool(token) and app.state.sessions.review_token_ok(session, token)

    def full_view(session: str, request: Request) -> bool:
        """A review token opens the re-identified view only with the session's own token (the
        browser that created it), an API key, or a supervisor key."""
        if API_KEYS and _bearer(request) in API_KEYS:
            return True
        token = request.headers.get("x-socareguard-session-token") or request.query_params.get(
            "token"
        )
        if token and app.state.sessions.token_ok(session, token):
            return True
        who = supervisor_identity(request)
        return bool(who and who[1])

    def reviewed(session: str, request: Request) -> tuple[Any, bool]:
        """(result, full) for a GET route. A valid review token opens the session read-only;
        otherwise the API key and session token rules of ``authorised`` apply."""
        if review_ok(session, request):
            res = app.state.sessions.get(session)
            if not res:
                raise HTTPException(404, "unknown session")
            return res, full_view(session, request)
        _require_key(request)
        return authorised(session, request), True

    def stand_in_pairs(session: str, res: Any) -> list[tuple[str, str]]:
        pairs = {
            (r["original"], r["outbound"])
            for r in res.replacements
            if r.get("original") and r.get("outbound") and r["original"] != r["outbound"]
        }
        pairs |= {
            (m.original, m.surrogate)
            for m in app.state.guard.vault.mappings(session)
            if m.original and m.surrogate and m.original != m.surrogate
        }
        return sorted((p for p in pairs if len(p[0]) > 1), key=lambda p: -len(p[0]))

    def pseudonymised_flags(session: str, res: Any, flags: Any = None) -> list[dict[str, Any]]:
        pairs = stand_in_pairs(session, res)
        out = []
        for f in res.flags if flags is None else flags:
            d = _flag_out(f)
            for k in ("evidence", "rewrite", "reason"):
                d[k] = _pseudonymise(d.get(k), pairs)
            out.append(d)
        return out

    def pseudonymised_events(res: Any) -> list[dict[str, Any]]:
        out = []
        for e in res.events:
            d = e.model_dump()
            if d.get("kind") not in _REVIEW_EVENTS:
                continue
            if d["kind"] == "leakcheck":
                d["leaks"] = []
            if d["kind"] == "generalise":
                # the count and the rule ids only; the spans quote the typed text
                d["rules"] = [
                    {"rule": r.get("rule"), "category": r.get("category")} for r in d["rules"]
                ]
            out.append(d)
        return out

    sweep()
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    templates = Jinja2Templates(directory=_HERE / "templates")
    scenarios = load_scenarios()

    @app.middleware("http")
    async def _origin_guard(request: Request, call_next):
        """The supervisor cookie is SameSite=None so that it holds in the Space's frame, which
        drops the protection SameSite=Strict gave against cross-site requests. This check puts it
        back for the requests that ``_csrf_guarded`` names."""
        if _csrf_guarded(request) and not _same_origin(request):
            return _openai_error(
                403, "cross-origin request refused: the origin is not this app", "bad_origin"
            )
        return await call_next(request)

    @app.exception_handler(HTTPException)
    async def _http_error(_request: Request, exc: HTTPException):
        return _openai_error(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError):
        # OpenAI answers a body it cannot parse or validate with 400, and so does the proxy.
        errors = exc.errors()
        if any(e.get("type") == "json_invalid" for e in errors):
            return _openai_error(400, BAD_JSON, "invalid_json")
        first = errors[0] if errors else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        return _openai_error(400, f"{loc}: {first.get('msg', 'invalid request')}", "invalid_body")

    def remember(session: str, res: Any, pack_id: str) -> str:
        """Index the session's latest result and return its token (the same token for every
        request in the session, across restarts)."""
        token = app.state.sessions.token(session) or uuid.uuid4().hex
        for old in app.state.sessions.put(session, res, token, pack_id):
            app.state.guard.vault.forget(old)
        return token

    @app.get("/", response_class=HTMLResponse)
    def panel(request: Request):
        # A signed-in supervisor (the sandbox login, a key sign-in or a supervisor key) sees the
        # release form on the read-only review of a withheld session. The cookie is HTTP-only, so
        # the page learns the identity from here.
        who = supervisor_identity(request)
        return templates.TemplateResponse(
            request,
            "panel.html",
            {
                "packs": available_packs(),
                "models": [DEFAULT_MODEL] + sorted(m for m in ALLOWED_MODELS if m != DEFAULT_MODEL),
                "sandbox": SANDBOX,
                "scenarios": scenarios,
                "scenarios_json": json.dumps(scenarios, ensure_ascii=False),
                "base_url": _base_url(request),
                "default_pack": DEFAULT_PACK,
                "auth_required": bool(API_KEYS),
                "supervisor_json": json.dumps(
                    {"actor": who[0], "attested": who[1]} if who else None
                ).replace("<", "\\u003c"),
                "precision_json": json.dumps(SCREEN_PRECISION),
                "taxonomy_json": json.dumps(
                    {
                        k: {
                            "name": c.name,
                            "plain": c.plain,
                            "clause": c.clause,
                            "clause_text": c.clause_text,
                        }
                        for k, c in BY_ID.items()
                    }
                ),
            },
        )

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "packs": available_packs(), "sandbox": SANDBOX}

    @app.get("/v1/models")
    def models(request: Request):
        _require_key(request)
        return {
            "object": "list",
            "data": [
                {"id": m, "object": "model", "created": 0, "owned_by": m.split("/")[0]}
                for m in [DEFAULT_MODEL] + sorted(x for x in ALLOWED_MODELS if x != DEFAULT_MODEL)
            ],
        }

    @app.get("/v1/packs")
    def packs(request: Request):
        _require_key(request)
        return {"packs": available_packs(), "default": DEFAULT_PACK}

    @app.get("/v1/packs/{pack_id}")
    def pack(pack_id: str, request: Request):
        _require_key(request)
        if pack_id not in available_packs():
            raise HTTPException(404, f"unknown pack {pack_id}")
        p = load_pack(pack_id)
        return {
            "id": p.id,
            "label": p.label,
            "version": p.version,
            "status": p.status,
            "legal_anchors": p.legal_anchors,
            "never_leak": p.outbound.never_leak,
            "attributes": [r.model_dump() for r in p.outbound.attributes],
            "quasi_identifiers": [r.model_dump() for r in p.outbound.quasi_identifiers],
            "categories": [c.model_dump() for c in p.inbound.categories],
            "override": p.override.model_dump(),
            "yaml": (PACK_DIR / f"{pack_id}.yaml").read_text(),
        }

    @app.post("/v1/chat/completions")
    def chat(
        req: ChatRequest,
        request: Request,
        response: Response,
        x_socareguard_pack: str | None = Header(default=None),
        x_socareguard_session: str | None = Header(default=None),
        x_socareguard_audience: str | None = Header(default=None),
    ):
        _require_key(request)
        audience = (x_socareguard_audience or "").lower() or None
        if audience not in (None, "internal", "care-team", "external", "auto"):
            raise HTTPException(
                400, "X-SoCareGuard-Audience must be internal, care-team, external or auto"
            )
        if not app.state.limiter.allow(_client_ip(request)):
            raise HTTPException(
                429,
                "rate limit: this sandbox allows a fixed number of requests per hour per address",
            )
        if req.stream:
            raise HTTPException(400, "streaming is not supported by the guardrail proxy")
        pack_id, pack_defaulted = x_socareguard_pack, False
        if not pack_id:
            pack_id, pack_defaulted = DEFAULT_PACK, True
        if pack_id not in available_packs():
            raise HTTPException(400, f"unknown pack {pack_id}")
        fixture = None
        if req.replay_scenario:
            fixture = _fixture_for(req.replay_scenario, req.replay_model)
            if fixture is None:
                raise HTTPException(
                    400,
                    f"no recorded reply for scenario {req.replay_scenario}"
                    + (f" from {req.replay_model}" if req.replay_model else ""),
                )
        if fixture is not None and fixture.get("model"):
            # A replay makes no provider call: the record names the model that wrote the reply.
            model, model_defaulted = fixture["model"], False
        else:
            model_defaulted = req.model not in ALLOWED_MODELS
            model = DEFAULT_MODEL if model_defaulted else req.model
        kwargs = {
            k: v
            for k, v in (("temperature", req.temperature), ("max_tokens", req.max_tokens))
            if v is not None
        }
        actor = _actor(request) + ("" if _attested(request) else " (self-asserted)")
        sweep()
        t0 = time.time()
        try:
            res = _run(req, pack_id, model, kwargs, x_socareguard_session, actor, fixture, audience)
        except HTTPException:
            raise
        except Exception as e:
            error_id = uuid.uuid4().hex[:8]
            _error_log.exception(
                "error %s: guarded request failed (pack %s, model %s, session %s)",
                error_id,
                pack_id,
                model,
                x_socareguard_session or "new",
            )
            raise HTTPException(
                503,
                f"the drafting model, the screen's model or the detectors failed ({type(e).__name__}, "
                f"error {error_id} in the server log). Nothing was sent to the practitioner and no "
                "draft was produced",
            ) from e
        token = remember(res.session, res, pack_id)
        if pack_defaulted:
            # A direct API caller that reads only the message content still sees the default.
            response.headers["X-SoCareGuard-Pack-Defaulted"] = "true"
        return _completion(
            res, model, pack_id, pack_defaulted, model_defaulted, actor, fixture, t0, token
        )

    def _run(req, pack_id, model, kwargs, session_header, actor, fixture, audience):
        return app.state.guard.run(
            req.messages,
            pack_id,
            model,
            session=session_header,
            provider_kwargs=kwargs,
            actor=actor,
            reply_fixture=fixture["text"] if fixture else None,
            reply_fixture_note=fixture.get("outbound_text") if fixture else None,
            seed=fixture["seed"] if fixture else None,
            audience=None if audience == "auto" else audience,
            audience_header=audience,
        )

    def _completion(
        res, model, pack_id, pack_defaulted, model_defaulted, actor, fixture, t0, token
    ):
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(t0),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "content_filter" if res.withheld else "stop",
                    "message": {"role": "assistant", "content": res.reply},
                }
            ],
            "usage": res.usage,
            "socareguard": {
                "session": res.session,
                "session_token": token,
                "pack": pack_id,
                "pack_defaulted": pack_defaulted,
                "model_defaulted": model_defaulted,
                "actor": actor,
                "decision": res.decision,
                "withheld": res.withheld,
                "flags": [_flag_out(f) for f in res.flags],
                "events": [e.model_dump() for e in res.events],
                "recipients": res.recipients,
                "replayed": bool(fixture),
                "recording": (
                    {
                        "model": fixture.get("model"),
                        "recorded_on": (fixture.get("recorded_at") or "")[:10],
                        "screened_with_recorded_note": bool(fixture.get("outbound_text")),
                    }
                    if fixture
                    else None
                ),
                "ledger_row_sha256": res.ledger_row["row_sha256"],
                "ledger_row": res.ledger_row,
                "latency_s": round(time.time() - t0, 1),
            },
        }

    @app.post("/v1/override")
    def override(req: OverrideRequest, request: Request):
        _require_key(request)
        if req.kind not in ("override", "rewrite_accepted"):
            raise HTTPException(400, "kind must be override or rewrite_accepted")
        res = authorised(req.session, request)
        if _reason_has_identifier(req.reason):
            raise HTTPException(400, REASON_IDENTIFIER)
        raised = {f.label for f in res.flags} | {f.label for f in res.flags_withheld}
        unknown = [f for f in req.flag_labels if f not in raised]
        if not req.flag_labels or unknown:
            raise HTTPException(
                400,
                "flag_labels must name flags raised on this session"
                + (f"; not raised: {', '.join(unknown)}" if unknown else ""),
            )
        # A later case review matches the row against the text that was kept, so a session with
        # a reply needs the hash of that text on every override, whoever the caller is.
        if res.reply and not _is_sha256(req.draft_sha256):
            raise HTTPException(400, DRAFT_HASH_REQUIRED)
        # The override points at a request row. It must be a row of this session in the ledger;
        # without one it points at the session's latest request row.
        request_row = req.request_row_sha256 or (res.ledger_row or {}).get("row_sha256")
        if request_row and not any(
            r.get("row_sha256") == request_row and r.get("session") == req.session
            for r in app.state.guard.ledger.rows()
        ):
            raise HTTPException(400, "request_row_sha256 must name a ledger row of this session")
        try:
            row = app.state.guard.override(
                req.session,
                _actor(request, req.by),
                req.flag_labels,
                req.reason,
                req.pack,
                request_row_sha256=request_row,
                kind=req.kind,
                attested=_attested(request),
                draft_sha256=req.draft_sha256,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True, "ledger_row_sha256": row["row_sha256"], "ledger_row": row}

    @app.get("/v1/sessions/{session}")
    def session(session: str, request: Request):
        """The session's latest result. A review token (``X-SoCareGuard-Review-Token`` or
        ``?review=``) opens it read-only. With the review token alone the response is
        pseudonymised: no re-identified reply, flags quoted with stand-ins, and no detection or
        generalisation text. The session's own token, an API key or a supervisor key opens the
        full view."""
        res, full = reviewed(session, request)
        out = {
            "session": session,
            "view": "full" if full else "pseudonymised",
            "pack": app.state.sessions.pack(session),
            "decision": res.decision,
            "withheld": res.withheld,
            "ledger_row": res.ledger_row,
        }
        if full:
            out.update(
                flags=[_flag_out(f) for f in res.flags],
                events=[e.model_dump() for e in res.events],
                reply=res.reply,
            )
        else:
            out.update(flags=pseudonymised_flags(session, res), events=pseudonymised_events(res))
        return out

    @app.get("/v1/sessions/{session}/panel")
    def session_panel(session: str, request: Request):
        """Replacement table for the practitioner's own panel (originals stay on this server).
        With a review token alone it returns only the stand-ins that left (``marks``), never the
        originals."""
        res, full = reviewed(session, request)
        if not full:
            marks = [
                {k: r.get(k) for k in ("outbound", "category", "type", "kind", "rule")}
                for r in res.replacements
                if r.get("outbound")
            ]
            return {"session": session, "view": "pseudonymised", "marks": marks}
        derived = [
            {
                "original": m.original,
                "outbound": m.surrogate,
                "category": m.category,
                "type": "DIRECT",
                "kind": "derived",
                "rule": None,
            }
            for m in app.state.guard.vault.mappings(session)
            if m.kind == "derived"
        ]
        return {"session": session, "replacements": res.replacements + derived}

    @app.get("/v1/sessions/{session}/withheld")
    def session_withheld(
        session: str,
        request: Request,
        reason: str = Query(default=""),
    ):
        """The draft that an escalation withheld, released to a supervisor only.

        A signed-in supervisor releases it without the practitioner's session token: a supervisor
        key in the Authorization header, the cookie of a key sign-in, or (in a deployment without
        keys) the cookie of the sandbox login, which stands in for the role header and the token
        and is recorded as "admin (sandbox login)", typed in. Without a supervisor identity the
        release is refused: a practitioner's session token, an API key or a typed-in supervisor id
        (the ``X-SoCareGuard-Role`` header, which earlier versions accepted in the sandbox) releases
        nothing. A reason is required, as for an override.

        The reply is re-identified when the caller may open the full view of the session (its own
        token, an API key or a supervisor key); otherwise it carries the stand-ins, and ``view``
        says ``pseudonymised``."""
        who = supervisor_identity(request)
        if who is None:
            # A typed-in supervisor id is not a sign-in: the draft stays withheld until a
            # supervisor signs in (a supervisor key, or the sandbox login where no key is set).
            if _keys_configured():
                raise HTTPException(
                    403, "release requires a key listed in SOCAREGUARD_SUPERVISOR_KEYS"
                )
            raise HTTPException(
                403,
                "a withheld draft is released by a signed-in supervisor only: sign in at "
                "/supervisor and release it from the review page",
            )
        res = app.state.sessions.get(session)
        if not res:
            raise HTTPException(404, "unknown session")
        if not res.withheld:
            raise HTTPException(400, "nothing was withheld in this session")
        if not reason.strip():
            raise HTTPException(400, "a reason for the release is required")
        if _reason_has_identifier(reason):
            raise HTTPException(400, REASON_IDENTIFIER)
        actor, attested = who
        prior = [
            {"row_sha256": r["row_sha256"], "actor": r.get("actor"), "ts": r.get("ts")}
            for r in app.state.guard.ledger.rows()
            if r.get("session") == session and r.get("decision") == "withheld_released"
        ]
        row = app.state.guard.ledger.append(
            {
                "session": session,
                "actor": actor,
                "actor_attested": attested,
                "decision": "withheld_released",
                "override_reason": reason,
                "flags": [f.label for f in res.flags],
                "request_row_sha256": res.ledger_row["row_sha256"] if res.ledger_row else None,
                "prior_release_row_sha256": [p["row_sha256"] for p in prior] or None,
            }
        )
        if full_view(session, request):
            reply = res.reply_withheld
            flags = [_flag_out(f) for f in res.flags_withheld]
            view = "full"
        else:
            reply = _pseudonymise(res.reply_withheld, stand_in_pairs(session, res))
            flags = pseudonymised_flags(session, res, res.flags_withheld)
            view = "pseudonymised"
        return {
            "session": session,
            "view": view,
            "reply": reply,
            "flags": flags,
            "ledger_row": row,
            "prior_releases": prior,
        }

    @app.delete("/v1/sessions/{session}")
    def forget(session: str, request: Request):
        """Purge the session's identity map (PDPA s.25: cease retention once the purpose is served)."""
        _require_key(request)
        authorised(session, request)
        n = app.state.guard.vault.forget(session)
        app.state.sessions.pop(session)
        row = app.state.guard.ledger.append(
            {
                "session": session,
                "actor": _actor(request),
                "actor_attested": _attested(request),
                "decision": "session_purged",
                "mappings_removed": n,
            }
        )
        return {"ok": True, "mappings_removed": n, "ledger_row": row}

    @app.get("/v1/ledger")
    def ledger(
        request: Request,
        session: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
    ):
        if session and review_ok(session, request):
            rows = [r for r in app.state.guard.ledger.rows() if r.get("session") == session]
            return {"rows": rows[-limit:], "total": len(rows)}
        _require_key(request)
        rows = app.state.guard.ledger.rows()
        if session:
            if session in app.state.sessions:
                authorised(session, request)
            elif not (API_KEYS and _bearer(request) in API_KEYS):
                # The session's token is gone with the session; only a key holder may read on.
                raise HTTPException(
                    403, "this session is closed; an API key is required to read it"
                )
            rows = [r for r in rows if r.get("session") == session]
        elif not API_KEYS:
            # Without an API key the listing is per session only: rows carry session ids and
            # free-text override reasons, so one visitor must not browse another's.
            raise HTTPException(403, "pass ?session=<id> with its token, or configure API keys")
        return {"rows": rows[-limit:], "total": len(rows)}

    @app.get("/v1/ledger/verify")
    def verify(
        request: Request,
        expected_rows: int | None = Query(default=None, ge=0),
    ):
        """Recompute the hash chain and the sequence numbers. Pass ``expected_rows`` (the row
        count from the last shipped "ledger head" log line) to detect a cut tail. A rewrite of
        every row from some point onwards still verifies here; compare ``head_sha256`` with the
        shipped log to detect it."""
        _require_key(request)
        return chain_report(expected_rows)

    def chain_report(expected_rows: int | None = None) -> dict[str, Any]:
        r = app.state.guard.ledger.report(expected_rows)
        n = r["rows"]
        if r["ok"]:
            msg = f"chain intact over {n} rows"
        elif r["first_bad_row"] is not None:
            msg = f"chain broken at row {r['first_bad_row']} of {n}"
        elif r["first_seq_gap"] is not None:
            msg = f"sequence gap at row {r['first_seq_gap']} of {n}"
        else:
            msg = f"{expected_rows} rows expected, {n} found"
        return {
            **r,
            "message": msg,
            "scope": (
                "tamper-evident against edits and reordering; anchoring the head hash outside "
                "the host is the deployer's step (ship the server log)"
            ),
        }

    # ---------- HTML pages for a browser (the JSON routes above are unchanged) ----------
    @app.get("/ledger/check", response_class=HTMLResponse)
    def chain_page(request: Request):
        """The chain check as a page with a way back to the panel; /v1/ledger/verify is the
        same check as JSON."""
        _require_key(request)
        return templates.TemplateResponse(
            request,
            "chain.html",
            {"sandbox": SANDBOX, "r": chain_report(), "default_pack": DEFAULT_PACK},
        )

    @app.get("/packs/{pack_id}", response_class=HTMLResponse)
    def pack_page(pack_id: str, request: Request):
        """A policy pack shown as its YAML source file, with a way back to the panel;
        /v1/packs/{pack_id} is the same pack as JSON."""
        _require_key(request)
        if pack_id not in available_packs():
            raise HTTPException(404, f"unknown pack {pack_id}")
        p = load_pack(pack_id)
        return templates.TemplateResponse(
            request,
            "pack.html",
            {
                "sandbox": SANDBOX,
                "pack": p,
                "pack_id": pack_id,
                "packs": available_packs(),
                "yaml_text": (PACK_DIR / f"{pack_id}.yaml").read_text(),
                "file_name": f"policy-packs/{pack_id}.yaml",
                "default_pack": DEFAULT_PACK,
            },
        )

    @app.get("/packs", response_class=HTMLResponse)
    def packs_page(request: Request):
        return RedirectResponse(f"/packs/{DEFAULT_PACK}", status_code=303)

    # ---------- supervisor view ----------
    def summary_for(request: Request) -> tuple[dict[str, Any], dict[str, str]]:
        q = request.query_params
        raw = {k: q.get(k, "") for k in ("pack", "category", "actor", "kind", "since", "until")}
        try:
            limit = int(q.get("limit") or 200)
            since = parse_when(raw["since"])
            until = parse_when(raw["until"], end=True)
            summary = build_summary(
                app.state.guard.ledger,
                app.state.sessions,
                since=since,
                until=until,
                pack=raw["pack"] or None,
                category=raw["category"] or None,
                actor=raw["actor"] or None,
                kind=raw["kind"] or None,
                limit=max(1, min(limit, 1000)),
            )
        except ValueError as e:
            raise HTTPException(400, f"filter not understood: {e}") from e
        return summary, raw

    def login_page(
        request: Request, status: int = 200, error: str = "", cookie_lost: bool = False
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "supervisor.html",
            {
                "signed_in": False,
                "keyed": _keys_configured(),
                "sandbox": SANDBOX,
                "error": error,
                "cookie_lost": cookie_lost,
                "review_minutes": int(REVIEW_TTL_S // 60),
            },
            status_code=status,
        )

    @app.get("/supervisor", response_class=HTMLResponse)
    def supervisor_page(request: Request):
        """The supervisor view: the chain check, the drafts waiting for release, filter chips and
        one period of supervisor actions. Without a supervisor identity it shows the sign-in form
        (a supervisor key when keys are configured, the sandbox login otherwise)."""
        who = supervisor_identity(request)
        if who is None:
            # A sign-in redirects here with ?signin=1. Arriving without a sign-in after one means
            # that the browser did not keep the cookie (a frame whose cookies are blocked).
            lost = request.query_params.get("signin") == "1"
            return login_page(request, 403 if _bearer(request) else 200, cookie_lost=lost)
        try:
            summary, raw = summary_for(request)
            error = ""
        except HTTPException as e:
            summary, raw = build_summary(app.state.guard.ledger, app.state.sessions), {}
            error = str(e.detail)
        return templates.TemplateResponse(
            request,
            "supervisor.html",
            {
                "signed_in": True,
                "keyed": _keys_configured(),
                "sandbox": SANDBOX,
                "actor": who[0],
                "attested": who[1],
                "s": summary,
                "raw": raw,
                "groups": chip_groups(raw, summary["filters"]["options"], time.time()),
                "error": error,
                "review_minutes": int(REVIEW_TTL_S // 60),
                "kind_plural": KIND_PLURAL,
                "kind_singular": KIND_SINGULAR,
            },
        )

    @app.post("/supervisor/login")
    async def supervisor_login(request: Request):
        """Sign a supervisor in and set the supervisor cookie.

        With keys configured, the form takes a supervisor key (and an optional staff id), and the
        sandbox credential is refused. Without keys, the form takes the sandbox credential of
        ``socareguard.proxy.demo_login`` and the actor is recorded as "admin (sandbox login)".
        This is a simplistic authentication for demonstration purposes only, with a fixed
        shared credential and no rate limiting or lockout, and it must be replaced with
        proper authentication (per-user credentials or single sign-on, a supervisor role that
        the deployment checks, session expiry and audit) before any production deployment."""
        raw = await request.body()
        is_json = "json" in request.headers.get("content-type", "")
        try:
            if is_json:
                form = json.loads(raw or b"{}")
            else:
                form = {k: v[0] for k, v in parse_qs(raw.decode()).items()}
        except (ValueError, UnicodeDecodeError):
            form = {}
        if not isinstance(form, dict):
            form = {}

        def refuse(status: int, message: str):
            if is_json:
                return _openai_error(status, message)
            return login_page(request, status, message)

        if _keys_configured():
            key = str(form.get("key") or "")
            if not (SUPERVISOR_KEYS and key in SUPERVISOR_KEYS):
                return refuse(
                    403,
                    "The demonstration login is off in this deployment. Sign in with a key "
                    "listed in SOCAREGUARD_SUPERVISOR_KEYS.",
                )
            actor, attested = str(form.get("staff_id") or "").strip() or "supervisor key", True
        else:
            if not demo_login.credential_ok(
                str(form.get("username") or ""), str(form.get("password") or "")
            ):
                return refuse(401, "The name or the password is wrong.")
            actor, attested = demo_login.DEMO_ACTOR, False
        cookie = app.state.logins.start(actor, attested)
        resp: Response = (
            JSONResponse({"ok": True, "actor": actor, "attested": attested})
            if is_json
            else RedirectResponse("/supervisor?signin=1", status_code=303)
        )
        _set_supervisor_cookie(resp, request, cookie)
        return resp

    @app.post("/supervisor/logout")
    def supervisor_logout(request: Request):
        app.state.logins.end(request.cookies.get(demo_login.COOKIE))
        resp = RedirectResponse("/supervisor", status_code=303)
        # Cleared with the attributes it was set with; a Partitioned cookie is only replaced by
        # a Partitioned one.
        _set_supervisor_cookie(resp, request, "", clear=True)
        return resp

    @app.get("/v1/supervisor/summary")
    def supervisor_summary(request: Request):
        """The supervisor view as JSON: ``chain``, ``queue``, ``actions`` (newest first, up to
        ``limit``), ``counts`` by kind and ``filters``. Filters: ``since`` and ``until`` (a date,
        an ISO time, seconds or ``all``; the default is the last 7 days), ``pack``, ``category``,
        ``actor`` and ``kind``. Same gate as the page."""
        actor, attested = _supervisor(request)
        summary, _raw = summary_for(request)
        return {"actor": actor, "actor_attested": attested, **summary}

    @app.post("/v1/sessions/{session}/review-token")
    def review_token(session: str, request: Request):
        """A read-only review token for one session, valid for 30 minutes, behind the supervisor
        gate. Only its hash is kept, and a ``review_opened`` ledger row records who opened it.
        The token opens the GET routes of the session (the result, the panel and the ledger rows)
        and nothing else. Without the session's own token or a supervisor key it opens the
        pseudonymised view only."""
        actor, attested = _supervisor(request)
        res = app.state.sessions.get(session)
        if not res:
            raise HTTPException(404, "unknown session")
        token, expires = app.state.sessions.issue_review_token(session, actor, attested)
        row = app.state.guard.ledger.append(
            {
                "session": session,
                "pack": app.state.sessions.pack(session),
                "actor": actor,
                "actor_attested": attested,
                "decision": "review_opened",
                "review_expires": expires,
                "request_row_sha256": res.ledger_row["row_sha256"] if res.ledger_row else None,
            }
        )
        return {
            "session": session,
            "review_token": token,
            "expires": expires,
            "url": f"/?session={quote(session)}&review={token}",
            "ledger_row": row,
        }

    return app


app = create_app()
