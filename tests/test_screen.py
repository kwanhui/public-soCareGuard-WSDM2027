"""Screener with a fake judge: flags, decisions, screening on pseudonymised text, override rules."""

from pathlib import Path

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack
from socareguard.proxy.core import Guard
from socareguard.screen.judge import FakeJudge, JudgeFlag, build_prompt, parse
from socareguard.screen.rules import over_caution
from socareguard.screen.screener import Screener

NOTE = "Client Tan Wei Ming, NRIC S1234567D, case YC/2026/0412, at Woodgrove Secondary School."


def test_prompt_quotes_clauses_and_parse_filters_unknown_labels():
    pack = load_pack("domestic-violence")
    _system, user = build_prompt(pack, "Summarise.", "draft")
    assert "A.7.c" in user and "emotive or derogatory" in user and "DV-1" in user
    flags = parse(
        '{"flags": [{"label": "I1", "evidence": "x", "confidence": 0.9}, {"label": "ZZ", "evidence": "y"}]}',
        {"I1"},
    )
    assert [f.label for f in flags] == ["I1"] and flags[0].confidence == 0.9


def test_over_caution_rule_on_routine_task():
    f = over_caution(
        "Please book Room 3. If you or someone you know is in crisis, call the Samaritans of Singapore at 1767 or 999.",
        "Draft a two-sentence email to admin confirming this appointment",
    )
    assert f and f.label == "OVER_CAUTION"
    assert over_caution("Please book Room 3 for Thursday.", "Draft an email to admin") is None


def test_guard_screens_pseudonymised_text_and_annotates(tmp_path: Path):
    judge = FakeJudge(
        {
            "red flag": [
                JudgeFlag(
                    "I1",
                    "a clear red flag",
                    0.9,
                    "ambivalence about returning is common at this stage",
                    "blaming language",
                )
            ]
        }
    )
    g = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=Screener(judge=judge, use_baseline=False),
    )
    res = g.run(
        [{"role": "user", "content": "Write a frank summary.\n\n" + NOTE}],
        "domestic-violence",
        "openai/gpt-4.1-mini",
        reply_fixture="Summary: this is a clear red flag.",
        seed=1,
    )
    assert (
        judge.calls
        and "S1234567D" not in judge.calls[0]["draft"]
        and judge.calls[0]["instruction"] == "Write a frank summary."
    )
    assert [f.label for f in res.flags] == ["I1"] and res.decision == "annotate"
    assert res.ledger_row["flags"] == ["I1"] and res.ledger_row["decision"] == "annotate"
    screen = next(e for e in res.events if e.kind == "screen")
    assert screen.flags[0].clause == "A.7.c" and screen.flags[0].rewrite


def test_escalate_wins_and_cannot_be_overridden(tmp_path: Path):
    judge = FakeJudge(
        {
            "identif": [
                JudgeFlag("I14", "names the young person and the offence", 0.95, None, "CYPA")
            ]
        }
    )
    g = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=Screener(judge=judge, use_baseline=False),
    )
    res = g.run(
        [{"role": "user", "content": "Draft a referral.\n\n" + NOTE}],
        "youth-offending",
        "openai/gpt-4.1-mini",
        reply_fixture="Referral: this identifies the young person.",
        seed=2,
    )
    assert res.decision == "escalate"
    import pytest

    with pytest.raises(ValueError):
        g.override(res.session, "worker", ["I14"], "needed", "youth-offending")


def test_low_confidence_flags_are_dropped(tmp_path: Path):
    judge = FakeJudge({"maybe": [JudgeFlag("I2", "maybe", 0.3, None, "weak")]})
    s = Screener(judge=judge, use_baseline=False)
    flags, decision, _ = s.screen("maybe this", load_pack("disability"), 1, instruction="x")
    assert flags == [] and decision == "pass"


def test_audience_gate_for_disclosure_categories():
    from socareguard.screen.rules import audience_is_external

    assert audience_is_external("Draft a two-sentence email to admin confirming this appointment")
    assert audience_is_external("Draft a short note to the cafe supervisor introducing Priya")
    assert not audience_is_external(
        "Summarise this intake note and draft three next steps for the probation review."
    )
    assert not audience_is_external(
        "Write a frank case summary and a four-point plan for my supervisor."
    )
    judge = FakeJudge({"x": [JudgeFlag("I14", "names the youth", 0.99, None, "cypa")]})
    s = Screener(judge=judge, use_baseline=False)
    flags, decision, _ = s.screen(
        "x", load_pack("youth-offending"), 1, instruction="Summarise for the probation review."
    )
    assert flags == [] and decision == "pass"
    flags, decision, _ = s.screen(
        "x", load_pack("youth-offending"), 1, instruction="Draft a referral letter to the school."
    )
    assert [f.label for f in flags] == ["I14"] and decision == "escalate"
