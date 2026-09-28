"""A long attribute clause that keeps its sentence must not carry a name out verbatim.

Round 4 and round 5 of the stakeholder review kept the sentence of a long offence, disability,
diagnosis or protection-order clause and replaced only the words naming the condition. The
names inside such a clause were still dropped from substitution, so they reached the provider
as written. Each case below puts a name inside one kind of kept clause and checks that it never
appears in the outbound text and that a reply using its surrogate restores it."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from socareguard.inbound.restore import restore
from socareguard.ledger import Ledger
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack
from socareguard.proxy.app import create_app
from socareguard.proxy.core import Guard

CASES = [
    # (pack, attribute key, note, name inside the clause)
    (
        "youth-offending",
        "offence",
        (
            "Visit note. Mr Tan Wei Ming was referred by the school after he was picked up for shop"
            " theft with two friends at the mall last week. Plan: review in two weeks."
        ),
        "Tan Wei Ming",
    ),
    (
        "youth-offending",
        "offence",
        "Visit note. Order: 12 months probation for Mr Tan Wei Ming, 40 hours CSO. Review soon.",
        "Tan Wei Ming",
    ),
    (
        "youth-offending",
        "offence",
        (
            "Visit note. Recommendation: Mr Tan Wei Ming to complete a guidance programme for the shop"
            " theft. Review."
        ),
        "Tan Wei Ming",
    ),
    (
        "disability",
        "disability",
        (
            "Home visit. At time of visit I observed Mdm Wee Shu Fen seated in a power wheelchair near"
            " the front door of the flat. Plan: refer."
        ),
        "Wee Shu Fen",
    ),
    (
        "disability",
        "diagnosis",
        (
            "Home visit. Her son Mr Kumar Rajan has moderate intellectual disability and was diagnosed"
            " with autism spectrum disorder in childhood. Plan: refer."
        ),
        "Kumar Rajan",
    ),
    (
        "domestic-violence",
        "ppo",
        (
            "Session note. Informed Mdm Cheryl Low Zi Xuan of next steps re: PPO application and offered"
            " to accompany her to appointments at the court. Plan: follow up."
        ),
        "Cheryl Low Zi Xuan",
    ),
]


def _name_parts(name: str) -> list[str]:
    """The name and every two-token part of it ("Low Zi"): a surrogate may share one token by chance."""
    toks = name.split()
    return [name] + [" ".join(toks[i : i + 2]) for i in range(len(toks) - 1)]


@pytest.mark.parametrize(
    "pack,key,note,name", CASES, ids=[f"{c[1]}-{i}" for i, c in enumerate(CASES)]
)
def test_name_inside_a_kept_clause_is_substituted_and_restored(
    tmp_path: Path, pack, key, note, name
):
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack(pack), use_presidio=False, use_gliner=False)
    out = s.sanitise(note, session="k1", seed=5)
    clause = next(h for h, _, _ in out.replacements if h.category == f"ATTR:{key}")
    assert name in clause.text  # the name really sits inside the attribute clause
    for part in _name_parts(name):
        assert part not in out.text, (part, out.text)
    reply = "Draft: " + out.text
    assert name in restore(reply, vault, "k1").text


def test_proxy_never_sends_a_name_inside_a_kept_clause(tmp_path, monkeypatch):
    note = CASES[3][2]
    sent: list[str] = []

    def provider(model, messages, **kw):
        payload = "\n".join(m["content"] for m in messages if m["role"] == "user")
        sent.append(payload)
        return "Summary: " + payload, {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr("socareguard.proxy.core.complete", provider)
    guard = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
    )
    client = TestClient(create_app(guard))
    for audience in (None, "internal", "external"):
        headers = {"X-SoCareGuard-Pack": "disability"}
        if audience:
            headers["X-SoCareGuard-Audience"] = audience
        r = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Summarise this note.\n\n" + note}]},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        for part in _name_parts("Wee Shu Fen"):
            assert part not in sent[-1], (audience, part, sent[-1])
        assert "wheelchair" not in sent[-1]
        content = r.json()["choices"][0]["message"]["content"]
        if r.json()["socareguard"]["decision"] != "withhold":
            assert "Wee Shu Fen" in content, (audience, content)
    assert len(sent) == 3
