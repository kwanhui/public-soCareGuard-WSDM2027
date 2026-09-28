"""Never-leak entries in the policy packs, checked against the notes the round-1 DV advocate wrote.

Each pack label must name a control that exists: either a pattern that withholds the span, or
the entity categories whose substitution or generalisation already removes it."""

import re
from pathlib import Path

import pytest

from socareguard.outbound.sanitise import DIRECT_SURROGATES, QUASI_GENERALISERS, Sanitiser
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import available_packs, load_pack

# Round 1, DV advocate F1: the shelter's proper name sat in front of its address.
SHELTER_NOTE = (
    "Write a short case note summarising this contact for the file.\n\n"
    "Contact note, 15 Sep 2026. Client Farhana binti Zulkifli, 29, case ref FSC-2026-0511. Farhana"
    " is staying at Rumah Damai Womens Shelter, Blk 8 Lengkok Bahru, unit #05-33, since 10 Sep with"
    " her son (age 3). She said her husband Muhammad Rizal bin Osman has called her mobile eleven"
    " times since she left. A PPO was filed on 12 Sep; hearing set for 6 Oct 2026 at the Family"
    " Justice Courts. Safety plan: shelter address not to be shared with in-laws, new SIM card"
    " purchased, son's childcare informed only that family is relocating.\n\nAssessment: risk"
    " remains elevated due to repeated contact attempts. Client is coping and engaged with shelter"
    " programme."
)
# Round 1, DV advocate F3: a weekly visit, its time and the bus she takes.
ROUTINE_NOTE = (
    "Write a brief update note for the file.\n\n"
    "Update, 26 Sep 2026. Client Mdm Rosnah binti Karim, 30, case ref FSC-2026-1502. Rosnah"
    " mentioned she still visits her mother every Tuesday at 4pm at Blk 118 Bedok North Street 2,"
    " and takes the same 47 bus each time, before returning to her current residence. She has not"
    " told her husband Encik Salleh bin Kassim about this arrangement.\n\nAssessment: continue"
    " monitoring."
)


def _sanitise(tmp_path: Path, pack, note: str, session: str = "nl") -> str:
    s = Sanitiser(Vault(tmp_path / "v.sqlite"), pack, use_presidio=False, use_gliner=False)
    return s.sanitise(note, session=session, seed=1).text


def test_shelter_name_before_its_address_never_leaves(tmp_path: Path):
    out = _sanitise(tmp_path, load_pack("domestic-violence"), SHELTER_NOTE)
    for token in ("Rumah", "Damai", "Womens", "Shelter", "Lengkok", "05-33"):
        assert token not in out, (token, out)
    assert "[withheld: shelter location]" in out


def test_entity_cut_by_a_never_leak_span_keeps_its_outside_part(tmp_path: Path):
    """The pack pattern of round 1 starts at the word "Shelter": the facility entity it overlaps
    must still be generalised for the part in front of the withheld span."""
    pack = load_pack("domestic-violence")
    old = pack.model_copy(deep=True)
    entry = next(e for e in old.outbound.never_leak if e.label == "shelter address or unit")
    entry.pattern = (
        r"\b(?:shelter|refuge)\b[^.;\n]{0,30}\b(?:address|unit|block|blk)\b[^.;\n]{0,60}"
    )
    out = _sanitise(tmp_path, old, SHELTER_NOTE)
    for token in ("Rumah", "Damai", "Womens"):
        assert token not in out, (token, out)
    assert "a crisis shelter [withheld: shelter location]" in out, out


def test_routine_and_timing_details_are_withheld(tmp_path: Path):
    out = _sanitise(tmp_path, load_pack("domestic-violence"), ROUTINE_NOTE)
    for detail in ("Tuesday", "4pm", "47"):
        assert not re.search(rf"\b{detail}\b", out), (detail, out)
    assert "[routine detail withheld]" in out
    # the facts the draft needs stay: she visits her mother, and the husband does not know
    assert "visits her mother" in out and "has not told her husband" in out


@pytest.mark.parametrize(
    "phrase",
    [
        "She sees the counsellor every Friday.",
        "She drops the children off on weekdays at 7.30am.",
        "She fetches her son on Mondays at 3 pm.",
        "She takes bus 858 to work.",
        "She rides the MRT from Bedok to Raffles Place every morning.",
    ],
)
def test_routine_pattern_variants(tmp_path: Path, phrase: str):
    out = _sanitise(tmp_path, load_pack("domestic-violence"), phrase)
    assert "[routine detail withheld]" in out, out


def test_routine_pattern_leaves_plain_dates_alone(tmp_path: Path):
    note = "Home visit on 3 Sep 2026. Review in two weeks. She took the bus home."
    out = _sanitise(tmp_path, load_pack("domestic-violence"), note)
    assert "withheld" not in out, out


def test_new_phone_number_and_workplace_are_removed(tmp_path: Path):
    note = (
        "She bought a new SIM; her new number is 8123 4567. She works part-time at Golden Crust"
        " Bakery in Tampines, and her manager knows about the situation."
    )
    out = _sanitise(tmp_path, load_pack("domestic-violence"), note)
    assert "8123 4567" not in out and "4567" not in out, out
    assert "Golden Crust" not in out and "Tampines" not in out, out


_CATEGORIES = set(DIRECT_SURROGATES) | set(QUASI_GENERALISERS)


@pytest.mark.parametrize("pack_id", available_packs())
def test_every_never_leak_label_names_its_control(pack_id: str):
    pack = load_pack(pack_id)
    attrs = {f"ATTR:{r.key}" for r in pack.outbound.attributes}
    for entry in pack.outbound.never_leak:
        assert entry.pattern or entry.enforced_by, (pack_id, entry.label)
        if entry.pattern:
            re.compile(entry.pattern)
        for cat in entry.enforced_by:
            assert cat in _CATEGORIES or cat in attrs, (pack_id, entry.label, cat)


def test_a_void_deck_is_not_an_employer():
    """Round 1, DV advocate F7: a GLiNER EMPLOYER tag on "void deck" became "an employer"."""
    from socareguard.detect.pipeline import _sane
    from socareguard.detect.sg import Hit

    assert not _sane(Hit(0, 9, "void deck", "EMPLOYER", "gliner", 0.57))
    assert not _sane(Hit(0, 13, "the void deck", "EMPLOYER", "gliner", 0.57))
    assert _sane(Hit(0, 6, "bakery", "EMPLOYER", "gliner", 0.6))


def test_bracket_placeholders_are_never_invented_identifiers(tmp_path: Path):
    """Round 1, DV advocate F8: "[School Name]" was flagged as invented (I13) while "[Name of
    Crisis Shelter]" was not. A template slot without digits is never an identifier."""
    from socareguard.inbound.leakcheck import leak_check
    from socareguard.inbound.restore import Restored

    vault = Vault(tmp_path / "v.sqlite")
    for reply in (
        "Please share this with [Insert Primary School] staff only.",
        "She is staying at [Rainbow Crisis Shelter] for now.",
    ):
        res = leak_check(
            reply, Restored(reply, 0, []), vault, "p", set(), use_presidio=False, use_gliner=False
        )
        assert res.invented == [], (reply, res.invented)
    reply = "She attends Rainbow Primary School."
    res = leak_check(
        reply, Restored(reply, 0, []), vault, "p", set(), use_presidio=False, use_gliner=False
    )
    assert [x.text for x in res.invented] == ["Rainbow Primary School"]
