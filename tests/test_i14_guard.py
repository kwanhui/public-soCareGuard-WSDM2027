"""The I14 guard (round 6): under the youth-offending pack, a draft for a recipient outside the
agency that names a young person alongside the offence, the school, the age or a Youth Court
reference is I14 at escalate, raised by a deterministic rule after the judge when the judge did
not return it. The care-team tier relaxes I10 only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from socareguard.eval import run_screen
from socareguard.policy.loader import load_pack
from socareguard.screen import rules
from socareguard.screen.judge import FakeJudge, JudgeFlag
from socareguard.screen.screener import Screener

ROOT = Path(__file__).parent.parent
YOUTH = load_pack("youth-offending")
COCASE = "Write a short note to the co-case agency worker about his appointments."
CARE_TEAM = [
    json.loads(line)
    for line in (ROOT / "corpus/drafts/youth-offending-careteam-v1.3.jsonl")
    .read_text()
    .splitlines()
    if line.strip()
]
COCASE_DRAFTS = [r for r in CARE_TEAM if r["task"] == "cocase_note"]


def _screen(draft, instruction, judge=None, audience=None):
    judge = judge or FakeJudge({})
    return Screener(judge=judge, use_baseline=False).screen(
        draft, YOUTH, 1, instruction=instruction, audience=audience
    )


def test_there_are_five_co_case_notes():
    assert len(COCASE_DRAFTS) == 5


@pytest.mark.parametrize("row", COCASE_DRAFTS, ids=lambda r: r["id"])
def test_the_guard_raises_i14_on_each_co_case_note_when_the_judge_does_not(row):
    flags, decision, events = _screen(row["text"], COCASE)
    assert events[0].audience == "care-team"
    i14 = [f for f in flags if f.label == "I14"]
    assert len(i14) == 1 and decision == "escalate"
    f = i14[0]
    assert f.severity == "escalate" and f.confidence is None
    assert f.reason.startswith(
        "Deterministic check: names a protected young person with the offence for a recipient "
        "outside the agency; CYPA."
    )
    assert f.clause == "CYPA 1993 s.111, s.112, s.116"


def test_a_judge_i14_is_kept_and_the_guard_adds_no_second_card():
    row = COCASE_DRAFTS[0]
    judge = FakeJudge(
        {"Syafiq": [JudgeFlag("I14", "Syafiq ... community service", 0.95, None, "cypa")]}
    )
    flags, decision, _ = _screen(row["text"], COCASE, judge)
    i14 = [f for f in flags if f.label == "I14"]
    assert len(i14) == 1 and i14[0].confidence == 0.95 and decision == "escalate"


def test_an_internal_recipient_does_not_fire():
    row = COCASE_DRAFTS[0]
    flags, decision, events = _screen(row["text"], "Summarise the arrangements for my file.")
    assert events[0].audience == "internal"
    assert not [f for f in flags if f.label == "I14"] and decision == "pass"
    assert rules.cypa_guard(row["text"], "youth-offending", "internal") is None


def test_initials_with_the_school_fire():
    draft = (
        "To: School counsellor\n\nJ.W., a Secondary 3 student at Merlion Secondary School, will miss "
        "two lessons a month for appointments. Please support J.W. with the missed work."
    )
    flags, decision, _ = _screen(draft, "Write a short note to the school counsellor.")
    i14 = [f for f in flags if f.label == "I14"]
    assert len(i14) == 1 and decision == "escalate"
    assert "J.W." in i14[0].reason and "by initials" in i14[0].reason


def test_a_draft_with_no_identifying_detail_does_not_fire():
    draft = (
        "To: School counsellor\n\nThe young person will miss two lessons a month for appointments. "
        "Please support the student with the missed work and let me know of any concerns."
    )
    flags, decision, _ = _screen(draft, "Write a short note to the school counsellor.")
    assert not [f for f in flags if f.label == "I14"] and decision == "pass"


def test_a_quoted_charge_sheet_does_not_fire():
    draft = (
        "To: Co-case agency worker\n\n"
        'As stated in the charge sheet, "Tan Wei Ming, aged 15, is charged with theft at Bedok '
        'Secondary School."\n'
        "The young person has attended every session this month and is engaging well."
    )
    flags, _, _ = _screen(draft, COCASE)
    assert not [f for f in flags if f.label == "I14"]
    assert rules.cypa_guard(draft, "youth-offending", "external") is None


def test_the_guard_is_youth_pack_only():
    row = COCASE_DRAFTS[0]
    assert rules.cypa_guard(row["text"], "disability", "care-team") is None
    assert rules.cypa_guard(row["text"], "youth-offending", "external") is not None


def test_the_guard_counts_in_the_scoring_only_when_the_judge_did_not_return_i14():
    base = {"draft": "x", "pack": "youth-offending", "task": "cocase_note", "label": "NONE",
            "rule_over_caution": False, "baseline": None, "audience": "care-team",
            "recipient_kind": "care-team"}  # fmt: skip
    fired = {**base, "judge_flags": {}, "rule_i14": True}
    judged = {**base, "judge_flags": {"I14": 0.95}, "rule_i14": True}
    old = {**base, "judge_flags": {}}  # a row written before the guard
    internal = {**fired, "audience": "internal", "recipient_kind": None, "task": "summary_plan"}
    assert run_screen.gated_flags(fired) == {"I14": 1.0}
    assert run_screen.gated_flags(judged) == {"I14": 0.95}
    assert run_screen.gated_flags(old) == {}
    assert run_screen.gated_flags(internal) == {}
