"""Round 5 of the second review set (2026-09-28): inbound defects on the reviewers' own letters."""

import pytest

from socareguard.detect.gazetteers import find_schools
from socareguard.policy.loader import load_pack
from socareguard.scenarios.events import DetectedSpan
from socareguard.screen import rules
from socareguard.screen.judge import FakeJudge
from socareguard.screen.screener import Screener

# The meta-reviewer's reply (wsdm-7-own-note.json) and the youth advocate's released letter
# (youth-3-withheld-released.json), from their first line to the salutation.
META_LETTER = (
    "[Your Organization’s Letterhead]  \n27 September 2026  \n\nSchool Counsellor  \n"
    "[School Name]  \n[School Address]  \n\nDear School Counsellor,  \n\nI am writing in my "
    "capacity as the attending social worker for Dhanush, a student at your school."
)
ADVOCATE_LETTER = (
    "[Your Name]  \n[Your Position]  \n[Your Contact Information]  \n[Date]\n\nSchool Counsellor  \n"
    "[School Name]  \n[School Address]\n\nDear School Counsellor,\n\n**Re: Referral for "
    "Counselling Support – Aisyah binte Karim, Sec 3**"
)


# META-N1, YOUTH-I13: "Dear School Counsellor" matched the school pattern and forced REGENERATE.


@pytest.mark.parametrize("letter", [META_LETTER, ADVOCATE_LETTER])
def test_a_salutation_is_not_a_school(letter):
    assert find_schools(letter) == [], find_schools(letter)


@pytest.mark.parametrize(
    "text,want",
    [
        ("Dear School Principal,", []),
        ("Please pass this to the School and to the counsellor.", []),
        ("He attends Fernvale Secondary School.", ["Fernvale Secondary School"]),
        ("Dear Principal of Northlight School,", ["Northlight School"]),
    ],
)
def test_school_pattern_needs_a_proper_noun_head(text, want):
    assert [h.text for h in find_schools(text)] == want


def _leak(text: str, category: str, detector: str) -> DetectedSpan:
    return DetectedSpan(
        start=0, end=len(text), text=text, type="DIRECT", category=category, detector=detector
    )


def test_a_general_pattern_alone_never_forces_regenerate():
    pack = load_pack("domestic-violence")
    s = Screener(judge=FakeJudge(), use_baseline=False)
    leaks = [_leak("Rosewood School", "SCHOOL", "sg.school")]
    flags, decision, _ = s.screen(META_LETTER, pack, 6, "Write a short letter", leaks=leaks)
    assert decision == "annotate", decision
    (i13,) = [f for f in flags if f.label == "I13"]
    assert i13.severity == "annotate" and i13.reason.strip(), i13


def test_an_invented_nric_still_regenerates_with_a_reason():
    pack = load_pack("youth-offending")
    s = Screener(judge=FakeJudge(), use_baseline=False)
    leaks = [_leak("T1234567J", "NRIC", "sg.nric")]
    _, decision, _ = s.screen("Her NRIC is T1234567J.", pack, 6, "Write a note", leaks=leaks)
    assert decision == "regenerate", decision
    assert rules.invented_identifiers(leaks).reason.strip()


# YOUTH-N1: initials in place of a name defeated I14 although the school could tell who was meant.
# The advocate's letter as the drafting model wrote it (youth-7-initials-school-letter.json).
INITIALS_LETTER = (
    "I am writing to inform you about the status of a probation client currently enrolled at your "
    "school, identified here as J.W., aged between 15 and 17 years, currently in Secondary 3.  \n\n"
    "J.W. was cautioned on 5 August 2026 in relation to a property offence."
)


def _hints(draft: str, pack_id: str, audience: str) -> list[str]:
    judge = FakeJudge()
    Screener(judge=judge, use_baseline=False).screen(
        draft, load_pack(pack_id), 6, "Write a letter to the school", audience=audience
    )
    return judge.calls[0]["hints"]


def test_initials_with_school_age_and_offence_are_a_hint_for_i14():
    (hint,) = _hints(INITIALS_LETTER, "youth-offending", "external")
    assert "initials (J.W.)" in hint and "a school, an age and an offence" in hint, hint


@pytest.mark.parametrize(
    "draft,pack,audience",
    [
        (INITIALS_LETTER, "youth-offending", "internal"),
        (INITIALS_LETTER, "domestic-violence", "external"),
        ("Dear Sir/Madam, the student will attend the camp.", "youth-offending", "external"),
        ("J.W. will attend the camp on Friday.", "youth-offending", "external"),
    ],
)
def test_no_initials_hint_without_context_or_outside_the_youth_pack(draft, pack, audience):
    assert _hints(draft, pack, audience) == []


def test_youth_pack_notes_cover_initials_and_quoted_charge_sheets():
    notes = {c.id: c.note for c in load_pack("youth-offending").inbound.categories}
    assert "Initials identify the young person" in notes["I14"]
    assert "a quotation is never I2" in notes["I2"]


# META-N3: the UC1 chip text did not say that the live judge may annotate the recorded reply.


def test_uc1_chip_text_names_the_possible_i11_annotation():
    import json
    from pathlib import Path

    from socareguard.scenarios.authoring import uc1

    root = Path(__file__).resolve().parents[1]
    header = json.loads(
        (root / "demo/sample-inputs/scenarios/uc1-youth-offending.jsonl")
        .read_text()
        .splitlines()[0]
    )
    assert header["summary"] == json.loads(uc1()[0])["summary"]
    assert header["summary"].endswith(
        "may also flag the recorded reply for its consent wording (I11)."
    )
    assert header["summary"] in (root / "demo/scenarios.md").read_text()
