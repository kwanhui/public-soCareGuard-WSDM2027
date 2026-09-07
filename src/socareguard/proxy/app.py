"""FastAPI app exposing an OpenAI-compatible ``/v1/chat/completions``.

Headers: ``X-SoCareGuard-Pack`` (disability | domestic-violence | youth-offending; falls back to
``SOCAREGUARD_DEFAULT_PACK`` and says so in the response), optional ``X-SoCareGuard-Session``
and ``X-SoCareGuard-Actor`` (the staff identity the ledger records). When ``SOCAREGUARD_API_KEYS``
is set, every ``/v1`` route requires ``Authorization: Bearer <key>``. The response is the
standard chat completion object plus a ``socareguard`` field carrying the event stream, flags,
recipients and the ledger row, which the transparency panel renders.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from socareguard.policy.loader import PACK_DIR, available_packs, load_pack
from socareguard.proxy.core import Guard
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
TRUST_PROXY = os.environ.get("SOCAREGUARD_TRUST_PROXY", "0") == "1"  # honour X-Forwarded-For
RETENTION_HOURS = float(
    os.environ.get("SOCAREGUARD_RETENTION_HOURS", "24" if SANDBOX else "0")
)  # 0 = keep until purged by DELETE /v1/sessions/{id}
MAX_PER_HOUR = int(os.environ.get("SOCAREGUARD_MAX_REQUESTS_PER_HOUR", "0"))  # 0 = unlimited
MAX_SESSIONS = int(os.environ.get("SOCAREGUARD_MAX_SESSIONS", "500"))
_HERE = Path(__file__).resolve().parent
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
                }
            )
    # The audience gate: one note, two audiences. Built on the disability scenario so the
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
                    "offence to an external audience escalates (I14): the draft is withheld from "
                    "this screen and only a supervisor can release it, with a reason, in the ledger."
                ),
                "instruction": (
                    "Write an email to the school principal explaining Amirul's court case and "
                    "probation conditions so the school can manage him."
                ),
                "note": uc1["note"],
                "compare_instruction": None,
                "has_recording": (_SCENARIO_DIR / "escalation.jsonl").exists(),
            }
        )
    uc3 = next((s for s in out if s["id"] == "uc3-disability"), None)
    if uc3 is not None:
        out.append(
            {
                "id": "audience-gate",
                "pack": uc3["pack"],
                "use_case": 5,
                "title": "Audience gate: the same note for the case file and for an employer",
                "short": "Audience gate",
                "summary": (
                    "The same care-plan note is drafted twice: once as a summary for the "
                    "practitioner's own case record, once as an introduction to a cafe supervisor. "
                    "Disclosure categories apply only to the external audience."
                ),
                "instruction": uc3["instruction"],
                "note": uc3["note"],
                "compare_instruction": (
                    "Summarise this care plan update for my own case record and list the next steps."
                ),
                "has_recording": False,
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
    replay_scenario: str | None = None  # panel only: reuse a scenario's recorded model reply


def _fixture_for(scenario_id: str) -> dict[str, Any] | None:
    """The recorded reply and seed of a shipped scenario, so the demo can replay the provider
    call deterministically. The guard itself still runs live."""
    f = _SCENARIO_DIR / f"{scenario_id}.jsonl"
    if not f.exists():
        return None
    seed, text = None, None
    for line in f.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("kind") == "user_turn" and seed is None:
            seed = d.get("seq")
        elif d.get("kind") == "receive" and text is None:
            text = d.get("text")
    return {"seed": seed, "text": text} if text else None


class OverrideRequest(BaseModel):
    session: str
    pack: str
    by: str | None = None
    flag_labels: list[str]
    reason: str
    kind: str = "override"  # override | rewrite_accepted
    request_row_sha256: str | None = None
    draft_sha256: str | None = None  # hash of the text the practitioner kept or applied


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


def create_app(guard: Guard | None = None) -> FastAPI:
    app = FastAPI(title="SoCareGuard", version="0.2.0")
    app.state.guard = guard or Guard()
    app.state.sessions: OrderedDict[str, Any] = OrderedDict()
    app.state.tokens: dict[str, str] = {}  # session -> token held by the client that made it
    app.state.limiter = RateLimiter(MAX_PER_HOUR)
    app.state.last_sweep = 0.0

    def sweep() -> None:
        if RETENTION_HOURS <= 0 or time.time() - app.state.last_sweep < 600:
            return
        app.state.last_sweep = time.time()
        n = app.state.guard.vault.purge_older_than(RETENTION_HOURS * 3600)
        cutoff = time.time() - RETENTION_HOURS * 3600
        old = [
            s
            for s, res in app.state.sessions.items()
            if (res.ledger_row or {}).get("ts", time.time()) < cutoff
        ]
        for s in old:
            app.state.sessions.pop(s, None)
            app.state.tokens.pop(s, None)
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
        if not token or token != app.state.tokens.get(session):
            raise HTTPException(403, "this session belongs to another client")
        return res

    sweep()
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    templates = Jinja2Templates(directory=_HERE / "templates")
    scenarios = load_scenarios()

    @app.exception_handler(HTTPException)
    async def _http_error(_request: Request, exc: HTTPException):
        return _openai_error(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        return _openai_error(422, f"{loc}: {first.get('msg', 'invalid request')}", "invalid_body")

    def remember(session: str, res: Any) -> None:
        app.state.sessions[session] = res
        app.state.sessions.move_to_end(session)
        while len(app.state.sessions) > MAX_SESSIONS:
            old, _ = app.state.sessions.popitem(last=False)
            app.state.guard.vault.forget(old)

    @app.get("/", response_class=HTMLResponse)
    def panel(request: Request):
        return templates.TemplateResponse(
            request,
            "panel.html",
            {
                "packs": available_packs(),
                "models": [DEFAULT_MODEL] + sorted(m for m in ALLOWED_MODELS if m != DEFAULT_MODEL),
                "sandbox": SANDBOX,
                "scenarios": scenarios,
                "scenarios_json": json.dumps(scenarios, ensure_ascii=False),
                "base_url": str(request.base_url).rstrip("/"),
                "default_pack": DEFAULT_PACK,
                "auth_required": bool(API_KEYS),
                "taxonomy_json": json.dumps(
                    {
                        k: {"name": c.name, "clause": c.clause, "clause_text": c.clause_text}
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
        x_socareguard_pack: str | None = Header(default=None),
        x_socareguard_session: str | None = Header(default=None),
        x_socareguard_audience: str | None = Header(default=None),
    ):
        _require_key(request)
        audience = (x_socareguard_audience or "").lower() or None
        if audience not in (None, "internal", "external", "auto"):
            raise HTTPException(400, "X-SoCareGuard-Audience must be internal, external or auto")
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
        fixture = _fixture_for(req.replay_scenario) if req.replay_scenario else None
        try:
            res = _run(req, pack_id, model, kwargs, x_socareguard_session, actor, fixture, audience)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                503,
                f"the drafting model, the conduct judge or the detectors failed ({type(e).__name__}); "
                "nothing was sent to the practitioner and no draft was produced",
            ) from e
        remember(res.session, res)
        token = app.state.tokens.setdefault(res.session, uuid.uuid4().hex)
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
                "flags": [f.model_dump() for f in res.flags],
                "events": [e.model_dump() for e in res.events],
                "recipients": res.recipients,
                "replayed": bool(fixture),
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
        authorised(req.session, request)
        try:
            row = app.state.guard.override(
                req.session,
                _actor(request, req.by),
                req.flag_labels,
                req.reason,
                req.pack,
                request_row_sha256=req.request_row_sha256,
                kind=req.kind,
                attested=_attested(request),
                draft_sha256=req.draft_sha256,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True, "ledger_row_sha256": row["row_sha256"], "ledger_row": row}

    @app.get("/v1/sessions/{session}")
    def session(session: str, request: Request):
        _require_key(request)
        res = authorised(session, request)
        return {
            "session": session,
            "decision": res.decision,
            "withheld": res.withheld,
            "flags": [f.model_dump() for f in res.flags],
            "events": [e.model_dump() for e in res.events],
            "reply": res.reply,
        }

    @app.get("/v1/sessions/{session}/panel")
    def session_panel(session: str, request: Request):
        """Replacement table for the practitioner's own panel (originals stay on this server)."""
        _require_key(request)
        res = authorised(session, request)
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
        x_socareguard_role: str | None = Header(default=None),
        reason: str = Query(default=""),
    ):
        """The re-identified draft that an escalation withheld, released to a supervisor only.
        A supervisor is not the practitioner, so this route does not take the session token: with
        API keys configured it needs a supervisor key; in a sandbox the role is self-asserted and
        the ledger row says so. A reason is required, as for an override."""
        _require_key(request)
        res = app.state.sessions.get(session)
        if not res:
            raise HTTPException(404, "unknown session")
        if not res.withheld:
            raise HTTPException(400, "nothing was withheld in this session")
        if (x_socareguard_role or "").lower() != "supervisor":
            raise HTTPException(403, "a withheld draft is released to a supervisor only")
        if API_KEYS and _bearer(request) not in SUPERVISOR_KEYS:
            raise HTTPException(403, "release requires a key listed in SOCAREGUARD_SUPERVISOR_KEYS")
        if not reason.strip():
            raise HTTPException(400, "a reason for the release is required")
        attested = bool(API_KEYS) and _bearer(request) in SUPERVISOR_KEYS
        row = app.state.guard.ledger.append(
            {
                "session": session,
                "actor": _actor(request) + ("" if attested else " (self-asserted supervisor)"),
                "actor_attested": attested,
                "decision": "withheld_released",
                "override_reason": reason,
                "flags": [f.label for f in res.flags],
                "request_row_sha256": res.ledger_row["row_sha256"] if res.ledger_row else None,
            }
        )
        return {
            "session": session,
            "reply": res.reply_withheld,
            "flags": [f.model_dump() for f in res.flags_withheld],
            "ledger_row": row,
        }

    @app.delete("/v1/sessions/{session}")
    def forget(session: str, request: Request):
        """Purge the session's identity map (PDPA s.25: cease retention once the purpose is served)."""
        _require_key(request)
        authorised(session, request)
        n = app.state.guard.vault.forget(session)
        app.state.sessions.pop(session, None)
        app.state.tokens.pop(session, None)
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
    def verify(request: Request):
        _require_key(request)
        ok, n = app.state.guard.ledger.verify()
        total = len(app.state.guard.ledger.rows())
        return {
            "ok": ok,
            "rows": total,
            "first_bad_row": None if ok else n,
            "message": (
                f"chain intact over {total} rows" if ok else f"chain broken at row {n} of {total}"
            ),
        }

    return app


app = create_app()
