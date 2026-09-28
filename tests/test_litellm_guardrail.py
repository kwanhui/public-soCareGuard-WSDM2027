"""The LiteLLM guardrail hooks run the same core as the app. Exercised with a fake response object."""

import asyncio
from types import SimpleNamespace

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.proxy.core import Guard
from socareguard.proxy.litellm_guardrail import SoCareGuardrail


def test_pre_and_post_hooks_roundtrip(tmp_path):
    g = SoCareGuardrail(pack="youth-offending")
    g.guard = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
    )
    data = {
        "model": "openai/gpt-4.1-mini",
        "messages": [
            {
                "role": "user",
                "content": "Client NRIC S1234567D, case YC/2026/0412, at Oakcrest Secondary School.",
            }
        ],
        "metadata": {},
    }
    out = asyncio.run(g.async_pre_call_hook(None, None, data, "completion"))
    sent = out["messages"][0]["content"]
    assert "S1234567D" not in sent and "YC/2026/0412" not in sent and "a secondary school" in sent
    assert out["metadata"]["socareguard_session"]
    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Summary: " + sent))]
    )
    back = asyncio.run(g.async_post_call_success_hook(out, None, resp))
    assert (
        "S1234567D" in back.choices[0].message.content
        and "YC/2026/0412" in back.choices[0].message.content
    )
    assert g.guard.ledger.verify()[0] and g.guard.ledger.rows()[-1]["leakcheck_passed"] is True
