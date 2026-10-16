"""Round-1 review finding F4 (2026-09-28): the capacity rule replaced a deputyship sentence and the plan
with the same predicate, so the deputyship never-leak rule never fired and the draft lost the deputy."""

from pathlib import Path

from socareguard.outbound.generalise import generalise_attribute
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack

WSDM_B2 = (
    "Draft a short letter to the HDB branch officer asking to renew Mr Lee's rental tenancy,"
    " explaining his situation.\n\n"
    "Review, 4 Sep 2026. Client Lee Kok Wai, NRIC S6543210H, 58, lives alone at Blk 88 Toa Payoh"
    " Lorong 4 #03-221. Diagnosis: schizophrenia, stable on clozapine, IMH follow-up. Capacity"
    " fluctuates: today he could not hold the options for the tenancy renewal across the session;"
    " last month he could. His sister Lee Mei Ling is his court-appointed deputy for property"
    " matters. He receives ComCare $600 per month. He wants to stay in the flat. Plan: liaise with"
    " the HDB officer on the tenancy renewal with the deputy present."
)


def _sanitise(tmp_path: Path, pack_id: str, note: str, session: str = "r1"):
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack(pack_id), use_presidio=False, use_gliner=False)
    return s.sanitise(note, session=session, seed=1), vault


def _sentence(text: str, start: str) -> str:
    i = text.index(start)
    return text[i : text.index(".", i)]


def test_capacity_rule_leaves_the_deputy_to_its_never_leak_rule_and_keeps_the_plan(tmp_path):
    out, _ = _sanitise(tmp_path, "disability", WSDM_B2)
    text = out.text
    assert "Lee Mei Ling" not in text and "Mei Ling" not in text, text
    assert "[withheld: deputyship or donee status; see record]" in text, text
    assert (
        "Plan: liaise with the HDB officer on the tenancy renewal with the deputy present" in text
    )
    assert text.count("apacity for this decision is in question") == 1, text
    assert "schizophrenia" not in text and "$600" not in text


def test_capacity_rule_scopes_to_the_capacity_clause():
    got = generalise_attribute(
        "capacity",
        "Plan: liaise with the HDB officer on the tenancy renewal with the deputy present",
        "status_only",
        "disability",
    )
    assert got.startswith("Plan: liaise with the HDB officer"), got
    got = generalise_attribute(
        "capacity",
        "Capacity fluctuates from week to week, so the review is set for when his sister can attend",
        "status_only",
        "disability",
    )
    assert "in question" in got and "the review is set for when his sister can attend" in got, got
