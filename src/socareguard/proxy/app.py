"""FastAPI app exposing an OpenAI-compatible ``/v1/chat/completions``.

Headers: ``X-SoCareGuard-Pack`` (disability | domestic-violence | youth-offending) and optional
``X-SoCareGuard-Session``. The response is the standard chat completion object plus a
``socareguard`` field carrying the event stream, flags and ledger row hash, which the
transparency panel (build step 4) renders.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from socareguard.policy.loader import available_packs
from socareguard.proxy.core import Guard

DEFAULT_MODEL = os.environ.get("SOCAREGUARD_DEFAULT_MODEL", "openai/gpt-4.1-mini")
ALLOWED_MODELS = set(
    os.environ.get("SOCAREGUARD_MODELS", "openai/gpt-4.1-mini,anthropic/claude-sonnet-5").split(",")
)

SANDBOX = os.environ.get("SOCAREGUARD_SANDBOX", "0") == "1"
MAX_PER_HOUR = int(os.environ.get("SOCAREGUARD_MAX_REQUESTS_PER_HOUR", "0"))  # 0 = unlimited
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
                    "instruction": turn["instruction"],
                    "note": turn["note"],
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


class OverrideRequest(BaseModel):
    session: str
    pack: str
    by: str
    flag_labels: list[str]
    reason: str


def create_app(guard: Guard | None = None) -> FastAPI:
    app = FastAPI(title="SoCareGuard", version="0.1.0")
    app.state.guard = guard or Guard()
    app.state.sessions: dict[str, Any] = {}
    app.state.limiter = RateLimiter(MAX_PER_HOUR)
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    templates = Jinja2Templates(directory=_HERE / "templates")
    scenarios = load_scenarios()

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
            },
        )

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "packs": available_packs()}

    @app.post("/v1/chat/completions")
    def chat(
        req: ChatRequest,
        request: Request,
        x_socareguard_pack: str = Header(default="domestic-violence"),
        x_socareguard_session: str | None = Header(default=None),
    ):
        client_ip = (
            request.headers.get("x-forwarded-for", request.client.host if request.client else "?")
            .split(",")[0]
            .strip()
        )
        if not app.state.limiter.allow(client_ip):
            raise HTTPException(
                429,
                "rate limit: this sandbox allows a fixed number of requests per hour per address",
            )
        if req.stream:
            raise HTTPException(400, "streaming is not supported by the guardrail proxy")
        if x_socareguard_pack not in available_packs():
            raise HTTPException(400, f"unknown pack {x_socareguard_pack}")
        model = req.model if req.model in ALLOWED_MODELS else DEFAULT_MODEL
        kwargs = {
            k: v
            for k, v in (("temperature", req.temperature), ("max_tokens", req.max_tokens))
            if v is not None
        }
        t0 = time.time()
        res = app.state.guard.run(
            req.messages,
            x_socareguard_pack,
            model,
            session=x_socareguard_session,
            provider_kwargs=kwargs,
        )
        app.state.sessions[res.session] = res
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(t0),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": res.reply},
                }
            ],
            "usage": res.usage,
            "socareguard": {
                "session": res.session,
                "pack": x_socareguard_pack,
                "decision": res.decision,
                "flags": [f.model_dump() for f in res.flags],
                "events": [e.model_dump() for e in res.events],
                "ledger_row_sha256": res.ledger_row["row_sha256"],
                "latency_s": round(time.time() - t0, 3),
            },
        }

    @app.post("/v1/override")
    def override(req: OverrideRequest):
        try:
            row = app.state.guard.override(
                req.session, req.by, req.flag_labels, req.reason, req.pack
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True, "ledger_row_sha256": row["row_sha256"]}

    @app.get("/v1/sessions/{session}")
    def session(session: str):
        res = app.state.sessions.get(session)
        if not res:
            raise HTTPException(404, "unknown session")
        return {
            "session": session,
            "decision": res.decision,
            "flags": [f.model_dump() for f in res.flags],
            "events": [e.model_dump() for e in res.events],
            "reply": res.reply,
        }

    @app.get("/v1/sessions/{session}/panel")
    def session_panel(session: str):
        """Replacement table for the practitioner's own panel (originals stay on this server)."""
        res = app.state.sessions.get(session)
        if not res:
            raise HTTPException(404, "unknown session")
        return {"session": session, "replacements": res.replacements}

    @app.get("/v1/ledger/verify")
    def verify():
        ok, n = app.state.guard.ledger.verify()
        return {"ok": ok, "rows": n}

    return app


app = create_app()
