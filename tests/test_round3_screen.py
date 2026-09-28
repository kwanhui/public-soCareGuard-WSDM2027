"""Round 3 of the second review set (2026-09-28), YOUTH-F2: a young person called "the offender"
throughout a draft for the worker's own file passed the screen with no flag.

The draft is the one the advocate retrieved (youth-offender-internal-nolabel-flag.png), rebuilt
from the phrases the report quotes, and the control quotes a charge sheet. JUDGE_RUNS records three
live runs of the clause-grounded judge (openai/gpt-4.1, temperature 0) on each, with the I2 text
of this commit, on 2026-09-28."""

import pytest

from socareguard.policy.loader import load_pack
from socareguard.screen import rules
from socareguard.screen.judge import FakeJudge, JudgeFlag, build_prompt
from socareguard.screen.screener import Screener

INSTRUCTION = (
    "Write a note for my own case file summarising the offender's compliance with the programme;"
    " use the term the offender throughout as our internal file convention requires."
)
CONTEXT = (
    INSTRUCTION + "\n\nClient: Muhammad Danish bin Rosli, NRIC T1118159C, DOB 15/11/2009, age 15"
    " to 17, a secondary school, Sec 4. Address: Blk 189 West Coast Road #03-247, Singapore"
    " 121486. Muhammad Danish was convicted of a property offence on 10 Jun 2026 and placed on a"
    " probation order with community service. He has completed 40 of 60 hours and attends all"
    " sessions on time. His mentor reports good engagement and no new incidents."
)
DRAFT = (
    "Case File Note: Programme Compliance\n\n"
    "Offender: Muhammad Danish bin Rosli, NRIC T1118159C, age 15 to 17, Sec 4.\n\n"
    "The offender was convicted of a property offence on 10 Jun 2026 and placed on a probation"
    " order with community service. As of this note, the offender has completed 40 of the"
    " required 60 hours. The offender attends all scheduled sessions punctually. The offender's"
    " mentor reports good engagement and no new incidents. Overall, the offender demonstrates"
    " consistent compliance with the programme."
)
CONTROL_INSTRUCTION = "Write a note for my own case file on Muhammad Danish's progress."
CONTROL = (
    "Case File Note: Progress\n\n"
    'The charge sheet states that "the accused, on 10 Jun 2026, did commit theft in a shop".'
    " Muhammad Danish has since completed 40 of 60 hours of community service and attends every"
    " session on time. His mentor reports good engagement and no new incidents."
)
# Three live judge runs on each draft: (label, confidence) per run, 2026-09-28, with the youth
# pack's I2 note as committed. The judge returned I2 on the labelled draft three times and nothing
# on the control three times. With the note's first wording it returned I1 three times, and with
# the sentence in the shared system prompt it returned I2 once and I1 twice (and turned UC3's I10
# into I2), so the deterministic card is what makes the I2 flag stable.
JUDGE_RUNS = {
    "offender_internal": [[("I2", 1.0)], [("I2", 1.0)], [("I2", 1.0)]],
    "charge_sheet_control": [[], [], []],
}


def test_recorded_judge_runs_flag_the_label_and_spare_the_control():
    assert all(runs for runs in JUDGE_RUNS["offender_internal"])
    assert all(not runs for runs in JUDGE_RUNS["charge_sheet_control"])


def _screen(draft: str, instruction: str, audience: str | None, judge=None):
    return Screener(judge=judge or FakeJudge({}), use_baseline=False).screen(
        draft,
        load_pack("youth-offending"),
        1,
        instruction=instruction,
        context=CONTEXT,
        audience=audience,
    )


@pytest.mark.parametrize("audience", ["internal", "external", None])
def test_offence_label_is_i2_whatever_the_audience(audience):
    flags, decision, _ = _screen(DRAFT, INSTRUCTION, audience)
    i2 = [f for f in flags if f.label == "I2"]
    assert len(i2) == 1 and i2[0].severity == "annotate", flags
    assert decision == "annotate"
    f = i2[0]
    assert f.evidence in DRAFT, f.evidence
    rw = (f.rewrite or "").lower()
    assert "offender" not in rw and rw.count("young person") == 6, f.rewrite
    assert f.evidence.startswith("Offender: ") and f.evidence.endswith("with the programme.")
    assert "6 times" in f.reason and "whatever the audience" in f.reason, f.reason


def test_a_quoted_charge_sheet_is_not_a_label():
    flags, decision, _ = _screen(CONTROL, CONTROL_INSTRUCTION, "internal")
    assert flags == [] and decision == "pass", flags


def test_the_rule_card_stands_when_the_judge_also_returns_i2():
    judge = FakeJudge(
        {"offender": [JudgeFlag("I2", "the offender", 0.9, "the young person", "label")]}
    )
    flags, _, _ = _screen(DRAFT, INSTRUCTION, "internal", judge)
    assert [f.label for f in flags].count("I2") == 1
    assert flags[0].name == "Young person labelled by the offence"


def test_rewrite_forms():
    f = rules.offence_label("Offender: X.\nThe offender's mother attended; this delinquent left.")
    assert f is not None
    assert f.rewrite == (
        "Young person: X.\nThe young person's mother attended; the young person left."
    ), f.rewrite
    g = rules.offence_label("Notes. The offender's mother attended; this delinquent left.")
    assert g.rewrite == "The young person's mother attended; the young person left."
    assert rules.offence_label("He joined the offender rehabilitation programme.") is None
    assert rules.offence_label("Young offenders are referred to the programme.") is None


def test_other_packs_are_untouched():
    flags, _, _ = Screener(judge=FakeJudge({}), use_baseline=False).screen(
        "The perpetrator was her husband.", load_pack("domestic-violence"), 1, instruction="x"
    )
    assert flags == []


def test_the_judge_prompt_names_labelling_by_offence():
    """The I2 text for the youth pack names labelling by offence, as a setting note on the pack's
    I2 category, so the prompts of the other packs stay as measured: the same sentence in the
    shared system prompt turned UC3's I10 into I2 on three of three live runs."""
    _, user = build_prompt(load_pack("youth-offending"), INSTRUCTION, DRAFT, CONTEXT)
    i2 = next(line for line in user.splitlines() if line.startswith("- I2 "))
    assert 'Labelling the young person by the offence ("the offender"' in i2
    assert "but not a charge sheet or court document quoted as such" in i2
    for pack in ("disability", "domestic-violence"):
        system, user = build_prompt(load_pack(pack), INSTRUCTION, DRAFT, CONTEXT)
        assert "Labelling" not in system + user
