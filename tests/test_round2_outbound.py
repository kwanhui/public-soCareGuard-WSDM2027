"""Round 2 of the second review set (2026-09-28): outbound defects on the reviewers' own notes.

Each test runs the reviewer's note with the NER hits recorded on it (tests/recorded_round2.py), so
the spans are the ones the sandbox produced."""

import re
from pathlib import Path

import pytest

from socareguard.outbound.generalise import generalise_attribute, generalise_facility
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.surrogates import SurrogateFactory, gender_evidence
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import available_packs, load_pack
from socareguard.proxy.core import _sanitise_message
from tests import recorded_round2 as rec


def _out(monkeypatch, tmp_path: Path, name: str, pack: str | None = None):
    note = rec.use(monkeypatch, name)
    s = Sanitiser(Vault(tmp_path / "v.sqlite"), load_pack(pack or note["pack"]))
    return _sanitise_message(s, note["text"], name, 7, 1)


def _surrogate(res, original: str) -> str:
    return next(new for h, new, _ in res.replacements if h.text == original)


# STU-F1: a surname that is also an estate, and a PPO rule that invented a hearing.


def test_student_surname_is_never_torn_out_of_a_name(monkeypatch, tmp_path):
    out = _out(monkeypatch, tmp_path, "student_8e").text
    assert "residential estate" not in out, out
    assert "Aljunied" not in out, out


def test_ppo_rule_never_invents_a_hearing_from_applied_for(monkeypatch, tmp_path):
    out = _out(monkeypatch, tmp_path, "student_8e").text
    assert "court hearing" not in out, out
    assert "The family has not applied for ComCare." in out, out
    assert generalise_attribute("ppo", "ComCare", "status_only", "domestic-violence") == "ComCare"
    assert (
        generalise_attribute(
            "ppo", "The family has not applied for ComCare", "status_only", "domestic-violence"
        )
        == "The family has not applied for ComCare"
    )
    # a hearing clause with its date still loses the date
    hearing = generalise_attribute(
        "ppo", "hearing set for 6 Oct 2026 at the Family Justice Courts", "status_only", "d"
    )
    assert "6 Oct" not in hearing and "Family Justice" not in hearing


def test_a_month_after_a_job_is_not_a_workplace(monkeypatch, tmp_path):
    out = _out(monkeypatch, tmp_path, "student_8e").text
    assert "lost his job as a delivery driver in July" in out, out
    assert "[workplace withheld]" not in out, out


def test_an_estate_on_its_own_is_still_generalised(tmp_path):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("domestic-violence"),
        use_presidio=False,
        use_gliner=False,
    )
    out = s.sanitise("She moved to a rental flat in Aljunied last month.", "est", seed=1).text
    assert "Aljunied" not in out and "a residential estate" in out, out


# STU-F3: a staff id typed into the note body.


def test_staff_id_in_the_note_body_is_substituted(monkeypatch, tmp_path):
    res = _out(monkeypatch, tmp_path, "student_9b")
    assert "SW-1042" not in res.text, res.text
    assert re.search(r"staff id SW-\d{4}\b", res.text), res.text
    cats = {h.category for h, _, _ in res.replacements}
    assert "STAFF_ID" in cats


@pytest.mark.parametrize(
    "text,staff",
    [
        ("Seen by officer id PO-2231 at the centre.", "PO-2231"),
        ("Recorded by MSW-0457 on the ward.", "MSW-0457"),
        ("Employee no. 104522 took the call.", "104522"),
    ],
)
def test_staff_id_formats(tmp_path, text, staff):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"), load_pack("disability"), use_presidio=False, use_gliner=False
    )
    out = s.sanitise(text, "sid", seed=1).text
    assert staff not in out, out


def test_case_references_are_not_staff_ids(tmp_path):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"), load_pack("disability"), use_presidio=False, use_gliner=False
    )
    res = s.sanitise("Client case CM-26-0331 and ref FSC-2026-0288.", "cr", seed=1)
    assert {h.category for h, _, _ in res.replacements} == {"CASE_REF"}


# FSC-F2 and MSW-F1: an amount is withheld by what it is, not by which word sits nearby.


def test_amounts_bind_to_the_phrase_they_label(monkeypatch, tmp_path):
    out = _out(monkeypatch, tmp_path, "fsc_5_arrears").text
    for amount in ("$650", "$1,240", "$310"):
        assert amount not in out, (amount, out)
    assert "Rental arrears at time of application: [withheld: amount]" in out, out
    assert "arrears reduced to [withheld: amount]" in out, out
    assert "improving with ComCare support" in out, out


@pytest.mark.parametrize("pack", available_packs())
@pytest.mark.parametrize(
    "sentence,amount",
    [
        ("Client's CPF Medisave balance is $12,340.50, insufficient for the bill.", "$12,340.50"),
        ("Her CPF Ordinary Account holds S$4,200.", "S$4,200"),
        ("MediShield Life paid out $3,100 last year.", "$3,100"),
        ("He receives Silver Support of $360 a quarter.", "$360"),
        ("HDB arrears of about $1,800 are outstanding.", "$1,800"),
        ("Household monthly income $1,850.", "$1,850"),
    ],
)
def test_financial_amounts_never_leave_in_any_pack(tmp_path, pack, sentence, amount):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"), load_pack(pack), use_presidio=False, use_gliner=False
    )
    out = s.sanitise(sentence, "amt", seed=1).text
    assert amount not in out, out
    assert "[withheld: amount]" in out, out


def test_an_amount_with_no_financial_label_stays(tmp_path):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("youth-offending"),
        use_presidio=False,
        use_gliner=False,
    )
    text = "Picked up for shop theft at a mall (items valued at about $80). ComCare was not discussed, and the fine was $80."
    out = s.sanitise(text, "amt2", seed=1).text
    assert "items valued at about $80" in out, out


def test_msw_cpf_balance_is_withheld(monkeypatch, tmp_path):
    out = _out(monkeypatch, tmp_path, "msw_2").text
    assert "$12,340.50" not in out and "$1,850" not in out and "$400" not in out, out


# MSW-F2: the diagnosis rewrite fits the grammar of the sentence it lands in.


def test_diagnosis_after_a_preposition_becomes_a_noun_phrase(monkeypatch, tmp_path):
    out = _out(monkeypatch, tmp_path, "msw_1").text
    assert "admitted for has" not in out, out
    assert "admitted for a physical disability sustained in a fall" in out, out
    assert "for mobility aid funding" in out, out


def test_diagnosis_rewrite_never_drops_a_clause_into_a_noun_slot(monkeypatch, tmp_path):
    out = _out(monkeypatch, tmp_path, "msw_4").text
    assert "for a has" not in out and "resulting has" not in out, out
    assert not re.search(r"\b(?:for|with|of|after|resulting) has\b", out), out


@pytest.mark.parametrize(
    "before,span,want",
    [
        ("Patient admitted for ", "C5 spinal cord injury", "a physical disability"),
        ("She ", "has schizophrenia", "has a psychiatric condition"),
        ("Mdm Tan ", "schizophrenia", "has a psychiatric condition"),
        ("He is ", "autistic", "living with a developmental disability"),
    ],
)
def test_grammar_slot_for_a_short_diagnosis_span(before, span, want):
    out = generalise_attribute("diagnosis", span, "category", "disability", before=before)
    assert out == want, out


# MSW-F5: a deputy's appointment is withheld as deputyship status, never read as a capacity doubt.


def test_deputy_appointment_is_withheld_not_rewritten_as_a_capacity_doubt(monkeypatch, tmp_path):
    out = _out(monkeypatch, tmp_path, "msw_5").text
    end = out.index("has consented")
    son = out[out.rindex(".", 0, end) + 1 : out.index(".", end)]
    assert "in question" not in son, son
    assert "[withheld: deputyship or donee status; see record]" in son, son
    assert "has consented to nursing home placement on her behalf" in son, son
    # the client's own capacity statement is untouched by the deputyship rule
    assert "Discharge plan:" in out, out


@pytest.mark.parametrize(
    "sentence",
    [
        "Her daughter Mdm Lim Siew Lan was appointed as deputy by the court last year.",
        "His brother is the court-appointed deputy for personal welfare.",
        "Her niece holds a Lasting Power of Attorney for property matters.",
        "Her son has been named donee under her LPA.",
    ],
)
def test_deputyship_phrasings_are_withheld(tmp_path, sentence):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"), load_pack("disability"), use_presidio=False, use_gliner=False
    )
    out = s.sanitise(sentence, "dep", seed=1).text
    assert "[withheld: deputyship or donee status; see record]" in out, out
    assert "in question" not in out, out


# MSW-F3, MSW-F4, MSW-F7 and the WSDM minors: places keep their kind, public bodies stay.


def test_a_hospital_department_is_not_an_employer(monkeypatch, tmp_path):
    out = _out(monkeypatch, tmp_path, "msw_1").text
    assert "an employer" not in out, out
    assert "Department of Rehabilitation Medicine" in out, out


def test_an_eldercare_home_is_not_a_youth_facility(monkeypatch, tmp_path):
    out = _out(monkeypatch, tmp_path, "msw_5").text
    assert "youth" not in out, out
    assert "St Joseph" not in out, out
    assert "a care facility" in out, out


@pytest.mark.parametrize(
    "name,want",
    [
        ("St Joseph's Home", "a care facility"),
        ("Meadowvale Boys' Home", "a youth residential facility"),
        ("Riverside Youth Residence", "a youth residential facility"),
        ("Bukit Merah Secondary School", "a secondary school"),
        ("Casa Harapan Crisis Shelter", "a crisis shelter"),
        ("Sunrise Nursing Home", "a care facility"),
    ],
)
def test_facility_fallback_is_type_neutral(name, want):
    assert generalise_facility(name) == want


def test_named_public_hospitals_stay(monkeypatch, tmp_path):
    for name in ("msw_3", "msw_4"):
        out = _out(monkeypatch, tmp_path / name, name).text
        assert "Tan Tock Seng Hospital" in out, out
        assert "a hospital" not in out, out


def test_an_invented_hospital_is_still_generalised(tmp_path):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"), load_pack("disability"), use_presidio=False, use_gliner=False
    )
    out = s.sanitise("Follow-up at Eastgate General Hospital next week.", "h", seed=1).text
    assert "Eastgate" not in out and "a hospital" in out, out


def test_a_street_name_is_never_a_person_and_a_school_keeps_its_level(monkeypatch, tmp_path):
    res = _out(monkeypatch, tmp_path, "wsdm_c_youth")
    assert "Jalan Membina" not in res.text, res.text
    names = [h.text for h, _, _ in res.replacements if h.category == "NAME"]
    assert not any(n.startswith("Jalan") for n in names), names
    assert "a service provider" not in res.text, res.text
    assert "Sec 3 at a secondary school" in res.text, res.text
    # round 6 acceptance F1: the instruction line is never generalised; the named school there
    # takes a stand-in, which the draft restores
    assert "Bukit Merah" not in res.text, res.text
    assert re.search(r"principal of [A-Z][a-z]+(?: [A-Z][a-z]+)* Secondary School", res.text), res.text


# FSC-F4: no bracketed placeholder number reaches the draft.


def test_no_numbered_placeholder_reaches_the_outbound_text(monkeypatch, tmp_path):
    out = _out(monkeypatch, tmp_path, "fsc_6_short").text
    assert not re.search(r"\(\d{1,2}\)", out), out
    assert "organisation (" not in out, out
    assert SurrogateFactory(1).generic("mall security") != "mall security"
    assert not re.search(r"\(\d+\)", SurrogateFactory(1).generic("mall security"))


# FSC-F1: a one-letter typo in a client's name is the same person.


def test_a_one_letter_typo_maps_to_the_same_surrogate(monkeypatch, tmp_path):
    res = _out(monkeypatch, tmp_path, "fsc_3_typo")
    full = _surrogate(res, "Suriati binti Yusof")
    typo = _surrogate(res, "Suriaty")
    assert typo == full.split()[0] or typo in full, (full, typo)


def test_a_typo_variant_is_found_without_a_ner_model(tmp_path):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("domestic-violence"),
        use_presidio=False,
        use_gliner=False,
    )
    res = s.sanitise(
        "Review note. Client: Mdm Suriati binti Yusof, 41.\n\nSuriaty called today to say she is coping.",
        "typo",
        seed=1,
    )
    assert "Suriaty" not in res.text and "Suriati" not in res.text, res.text


def test_edit_distance_needs_five_letters():
    f = SurrogateFactory(3)
    a = f.name("Tan Wei Ming")
    b = f.name("Tan Wei Ning")  # a different person: short tokens must match exactly
    assert a != b
    c = f.name("Suriati binti Yusof")
    d = f.name("Suriati binti Yusoff")
    assert c == d


# FSC-F6: a boy's surrogate reads as a boy's name.


def test_surrogate_given_name_follows_the_source_gender(monkeypatch, tmp_path):
    res = _out(monkeypatch, tmp_path, "fsc_1_household")
    assert gender_evidence(_surrogate(res, "Danish")) != "female"
    assert gender_evidence(_surrogate(res, "Amirah")) != "male"
    assert gender_evidence("Danish") == "male"
    assert gender_evidence("Ridzwan") == "male"


def test_relationship_word_sets_the_gender_when_the_pool_does_not_know_the_name(
    monkeypatch, tmp_path
):
    res = _out(monkeypatch, tmp_path, "student_8e")
    assert gender_evidence(_surrogate(res, "Ridzwan Aljunied")) != "female"
    assert gender_evidence(_surrogate(res, "Danial Aljunied")) != "female"
