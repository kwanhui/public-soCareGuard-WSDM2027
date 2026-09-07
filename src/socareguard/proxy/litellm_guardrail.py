"""SoCareGuard as a LiteLLM Proxy custom guardrail.

Register in the LiteLLM proxy config::

    guardrails:
      - guardrail_name: socareguard
        litellm_params:
          guardrail: socareguard.proxy.litellm_guardrail.SoCareGuardrail
          mode: [pre_call, post_call]
          default_on: true

The same ``Guard`` core runs in both hooks; the session id travels in ``metadata``.
"""

from __future__ import annotations

import uuid
from typing import Any

from socareguard.proxy.core import Guard

try:
    from litellm.integrations.custom_guardrail import CustomGuardrail
except ImportError:  # pragma: no cover - litellm proxy extras not installed

    class CustomGuardrail:  # type: ignore[no-redef]
        def __init__(self, **kwargs):
            pass


class SoCareGuardrail(CustomGuardrail):
    def __init__(self, pack: str = "domestic-violence", **kwargs):
        super().__init__(**kwargs)
        self.guard = Guard()
        self.pack = pack

    async def async_pre_call_hook(self, user_api_key_dict, cache, data: dict, call_type: str):
        meta = data.setdefault("metadata", {})
        pack = (
            meta.get("socareguard_pack")
            or (data.get("headers") or {}).get("x-socareguard-pack")
            or self.pack
        )
        session = meta.get("socareguard_session") or uuid.uuid4().hex[:12]
        out_msgs, _events, known, payload_hash, _payload, seq, _repl = self.guard.outbound(
            data["messages"], pack, session
        )
        data["messages"] = out_msgs
        meta.update(
            {
                "socareguard_session": session,
                "socareguard_pack": pack,
                "socareguard_known": sorted(known),
                "socareguard_seq": seq,
                "socareguard_payload_sha256": payload_hash,
            }
        )
        return data

    async def async_post_call_success_hook(self, data: dict, user_api_key_dict, response: Any):
        meta = data.get("metadata", {})
        session, pack = meta.get("socareguard_session"), meta.get("socareguard_pack", self.pack)
        if not session:
            return response
        choice = response.choices[0]
        raw = choice.message.content or ""
        r, lk, flags, decision, _events = self.guard.inbound(
            raw,
            session,
            set(meta.get("socareguard_known", [])),
            pack,
            meta.get("socareguard_seq", 10),
        )
        choice.message.content = r.text
        self.guard.ledger.append(
            {
                "session": session,
                "pack": pack,
                "model": data.get("model"),
                "payload_sha256": meta.get("socareguard_payload_sha256"),
                "n_restored": r.n_restored,
                "leakcheck_passed": lk.passed,
                "flags": [f.label for f in flags],
                "decision": decision,
            }
        )
        return response
