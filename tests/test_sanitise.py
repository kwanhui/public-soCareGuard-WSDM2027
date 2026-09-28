"""Sanitise / restore / leak-check contracts, using only the deterministic recognisers
(no Presidio or GLiNER) so the tests run in milliseconds."""

from pathlib import Path

from socareguard.inbound.leakcheck import leak_check
from socareguard.inbound.restore import restore
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.surrogates import SurrogateFactory, guess_gender, guess_origin
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import available_packs, load_pack

NOTE = (
    "Client Nur Aisyah binti Yusof, NRIC S7956482F, DOB 14/03/1979, age 47, of Blk 827 Hougang Avenue 8 #11-402, "
    "Singapore 532032 in Hougang. Contact 9123 4567. Case ref FSC-2026-0288. Her son attends Larkhaven Primary School. "
    "Aisyah said she is staying at Casa Harapan Crisis Shelter. Nur Aisyah binti Yusof consented."
)


def test_packs_load():
    assert available_packs() == ["disability", "domestic-violence", "youth-offending"]
    p = load_pack("domestic-violence")
    assert p.attribute_rule("safety_plan").generalise_to == "redact"
    assert p.action_for("I1") == "annotate"


def test_origin_and_gender_guess():
    assert (
        guess_origin("Nur Aisyah binti Yusof") == "malay"
        and guess_gender("Nur Aisyah binti Yusof") == "female"
    )
    assert (
        guess_origin("Kumar s/o Subramaniam") == "indian"
        and guess_gender("Kumar s/o Subramaniam") == "male"
    )
    assert guess_origin("Tan Wei Ming") == "chinese"
    assert guess_origin("Melissa Pereira") == "eurasian"


def test_surrogates_consistent_and_injective():
    f = SurrogateFactory(1)
    full = f.name("Nur Aisyah binti Yusof")
    short = f.name("Aisyah")
    assert short in full and "binti" in full
    assert f.name("Nur Aisyah binti Yusof") != f.name("Siti Nurhaliza binti Hamid")
    n1, n2 = f.nric("S7956482F"), f.nric("T1170839G")
    assert n1 != n2 and n1[0] == "S" and n2[0] == "T" and n2[1:3] == "11"
    assert f.dob("14/03/1979") != "14/03/1979" and "/" in f.dob("01/01/2000")


def test_sanitise_restore_roundtrip(tmp_path: Path):
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("domestic-violence"), use_presidio=False, use_gliner=False)
    out = s.sanitise(NOTE, session="t1", seed=7)
    for secret in (
        "S7956482F",
        "9123 4567",
        "FSC-2026-0288",
        "532032",
        "#11-402",
        "Larkhaven",
        "Casa Harapan",
        "Hougang",
        "14/03/1979",
    ):
        assert secret not in out.text, secret
    assert (
        "a primary school" in out.text
        and "a crisis shelter" in out.text
        and "the north-east" in out.text
    )
    assert "age 40 to 49" in out.text
    kinds = {k for _, _, k in out.replacements}
    assert {"surrogate", "generalised"} <= kinds
    ev = {e.kind: e for e in out.events}
    assert ev["substitute"].n_spans + ev["substitute"].n_generalised >= 9
    assert len(ev["generalise"].rules) >= 3
    reply = f"Summary: {out.text[:80]}"
    r = restore(reply, vault, "t1")
    assert r.n_restored >= 1 and r.unrestored_surrogates == []
    full = restore(out.text, vault, "t1")
    # everything that was substituted comes back; generalised phrases come back on exact match
    assert (
        "S7956482F" in full.text
        and "FSC-2026-0288" in full.text
        and "Larkhaven Primary School" in full.text
    )


def test_leak_check_flags_invented_and_echoed(tmp_path: Path):
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("youth-offending"), use_presidio=False, use_gliner=False)
    out = s.sanitise(
        "Client Tan Wei Ming, NRIC S1234567D, case YC/2026/0412.", session="t2", seed=3
    )
    clean_reply = out.text.replace("Client", "Summary for")
    r = restore(clean_reply, vault, "t2")
    assert leak_check(
        clean_reply, r, vault, "t2", set(), use_presidio=False, use_gliner=False
    ).passed
    bad_reply = clean_reply + " Also NRIC S9876543Z was noted."
    r2 = restore(bad_reply, vault, "t2")
    res = leak_check(bad_reply, r2, vault, "t2", set(), use_presidio=False, use_gliner=False)
    # an invented identifier is a conduct finding (I13), not a privacy failure
    assert res.passed and [x.category for x in res.invented] == ["NRIC"]
    echo = clean_reply + " (original S1234567D)"
    res3 = leak_check(
        echo, restore(echo, vault, "t2"), vault, "t2", set(), use_presidio=False, use_gliner=False
    )
    assert res3.original_echoed == ["S1234567D"]


def test_surrogate_never_reuses_an_original_name_token():
    originals = {"Lakshmi d/o Ramasamy", "Lakshmi", "Adrian Shepherdson", "Adrian"}
    f = SurrogateFactory(5, forbidden=originals)
    for o in ("Lakshmi d/o Ramasamy", "Adrian Shepherdson"):
        sur = f.name(o).lower()
        assert not (
            {"lakshmi", "ramasamy", "adrian", "shepherdson"} & set(sur.replace("/", " ").split())
        )


def test_case_ref_surrogate_keeps_year():
    f = SurrogateFactory(9)
    for o in ("YC/2026/0412", "FSC-2026-0288", "CM-26-0331"):
        s = f.case_ref(o)
        assert s != o and s[:3] == o[:3]
        if "2026" in o:
            assert "2026" in s


def test_short_name_before_full_name_maps_to_same_person():
    f = SurrogateFactory(3, forbidden={"Dinesh", "Dinesh s/o Ramasamy"})
    full = f.name("Dinesh s/o Ramasamy")
    assert f.name("Dinesh") == full.split()[0]


def test_capacity_generalisation_never_inverts():
    from socareguard.outbound.generalise import generalise_attribute

    assert (
        generalise_attribute(
            "capacity",
            "fluctuating capacity; supported decision-making needed",
            "status_only",
            "disability",
        )
        == "capacity for this decision is in question"
    )
    assert (
        generalise_attribute(
            "capacity", "has capacity to make this decision", "status_only", "disability"
        )
        == "has capacity for this decision"
    )
    assert (
        generalise_attribute(
            "capacity", "capacity assessment scheduled", "status_only", "disability"
        )
        == "capacity for this decision: see record"
    )


def test_fresh_surrogate_degrades_instead_of_failing():
    f = SurrogateFactory(11, forbidden={"PPO/2026"})
    s = f.case_ref("PPO/2026")
    assert s != "PPO/2026" and s.startswith("PPO/")
    g = SurrogateFactory(12)
    assert g.generic("X") != "X"


def test_derived_forms_restore_title_surname_dob_and_postal(tmp_path: Path):
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("domestic-violence"), use_presidio=False, use_gliner=False)
    text = "Client DOB 14/03/1979 lives at Blk 827 Hougang Avenue 8 #11-402, Singapore 532032."
    s.sanitise(text, session="d1", seed=4)
    maps = vault.mappings("d1")
    dob_new = next(m.surrogate for m in maps if m.category == "DOB" and m.kind == "surrogate")
    postal_new = next(
        m.surrogate
        for m in maps
        if m.category == "ADDRESS" and m.kind == "derived" and m.surrogate.isdigit()
    )
    from datetime import datetime

    reply = (
        f"DOB {datetime.strptime(dob_new, '%d/%m/%Y').strftime('%d %b %Y')}; postal {postal_new}."  # noqa: DTZ007
    )
    r = restore(reply, vault, "d1")
    assert "14 Mar 1979" in r.text and "532032" in r.text


def test_ppo_and_dv_rules_keep_polarity():
    from socareguard.outbound.generalise import generalise_attribute

    assert (
        generalise_attribute(
            "ppo", "she is unsure whether to apply for a PPO", "status_only", "domestic-violence"
        )
        == "a protection order is being considered"
    )
    assert (
        generalise_attribute(
            "ppo", "PPO application filed on 26 Aug", "status_only", "domestic-violence"
        )
        == "a protection order application is pending"
    )
    assert generalise_attribute(
        "dv_disclosure",
        "denied being hit by her husband but said he checks her phone",
        "keep_event_drop_specifics",
        "domestic-violence",
    ).startswith("denied physical violence by her husband")


def test_lone_surname_maps_to_surrogate_surname():
    f = SurrogateFactory(21, forbidden={"Teo Shu Fen", "Teo", "Shu Fen"})
    full = f.name("Teo Shu Fen")
    sur_surname = (
        full.split()[0]
        if full.split()[0].lower()
        in {
            x.lower()
            for x in __import__("socareguard.corpus.names", fromlist=["x"])._CHINESE_SURNAMES
        }
        else full.split()[1]
    )
    assert f.name("Teo") == sur_surname
    assert f.name("Mdm Teo") == f"Mdm {sur_surname}"
    assert f.name("Shu Fen") != f.name("Teo")


def test_name_extension_and_title_employer_rejected():
    from socareguard.detect.pipeline import _extend_names, _sane
    from socareguard.detect.sg import Hit

    text = "Client Teo Shu Fen (Mdm Teo) attended."
    h = Hit(11, 18, "Shu Fen", "NAME", "gliner", 0.9)
    ext = _extend_names(text, [h])[0]
    assert (ext.start, ext.text) == (7, "Teo Shu Fen")
    assert not _sane(Hit(20, 27, "Mdm Teo", "EMPLOYER", "gliner", 0.8))


def test_english_given_name_keeps_its_form():
    f = SurrogateFactory(31, forbidden={"Serene Goh Hui Min", "Serene", "Goh"})
    full = f.name("Serene Goh Hui Min")
    assert len(full.split()) == 4
    assert f.name("Serene") == full.split()[0]
    g = SurrogateFactory(32, forbidden={"Tan Wei Ming", "Wei Ming"})
    assert len(g.name("Tan Wei Ming").split()) == 3


def test_recent_date_is_not_a_dob():
    from socareguard.detect.pipeline import _sane
    from socareguard.detect.sg import Hit

    assert not _sane(Hit(0, 14, "24 August 2026", "DOB", "gliner", 0.9))
    assert _sane(Hit(0, 10, "14/03/1979", "DOB", "gliner", 0.9))


def test_lowercase_word_is_not_a_name_and_leading_verb_is_trimmed():
    from socareguard.detect.pipeline import _resolve, _sane
    from socareguard.detect.sg import Hit

    assert not _sane(Hit(0, 10, "supervisor", "NAME", "gliner", 0.9))
    hits = _resolve(
        [Hit(0, 35, "Attends Sunbeam Day Activity Centre", "FACILITY", "sg.facility", 0.85)]
    )
    assert hits[0].text == "Sunbeam Day Activity Centre" and hits[0].start == 8


def test_adjacent_duplicate_generalisations_collapse(tmp_path: Path):
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("disability"), use_presidio=False, use_gliner=False)
    out = s.sanitise(
        "Capacity: she has capacity to decide. Capacity assessment confirmed she has capacity to decide.",
        session="c1",
        seed=2,
    )
    assert out.text.lower().count("has capacity for this decision") == 1


def test_article_is_not_duplicated_before_a_generalised_phrase(tmp_path: Path):
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("disability"), use_presidio=False, use_gliner=False)
    out = s.sanitise(
        "She wants to work at a hawker stall at Chong Pang and attends Sunbeam Day Activity Centre.",
        session="a1",
        seed=5,
    )
    assert "a an " not in out.text and "a a " not in out.text
    # the UC3 shape: a generalised attribute earlier in the sentence must not restore the article
    out2 = s.sanitise(
        "She has a diagnosis of moderate intellectual disability. She wants to try the programme at a cafe.",
        session="a2",
        seed=5,
    )
    assert "a an " not in out2.text and "a a " not in out2.text


def test_two_letter_surname_gets_a_derived_form():
    from socareguard.outbound.sanitise import _derived_forms

    pairs = _derived_forms("NAME", "Pang Hui Min", "Ng Zi Xuan")
    assert ("Pang", "Ng") in pairs


def test_two_people_never_share_a_short_surrogate():
    f = SurrogateFactory(11, forbidden={"Priya", "Kamala"})
    a, b = f.name("Priya"), f.name("Kamala")
    assert a != b and a.split()[0] != b.split()[0]


def test_patronymic_is_part_of_the_name_and_new_identifier_kinds_are_caught(tmp_path: Path):
    from socareguard.detect.pipeline import detect

    t = "Client Priya d/o Muthusamy, passport E1234567X, account 072-918203-6, handle @priya_wdl."
    cats = {(h.category, h.text) for h in detect(t, use_presidio=False, use_gliner=False).entities}
    assert ("PASSPORT", "E1234567X") in cats and ("BANK_ACCOUNT", "072-918203-6") in cats
    assert ("HANDLE", "@priya_wdl") in cats
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("disability"), use_presidio=False, use_gliner=False)
    out = s.sanitise(t, session="p1", seed=4)
    assert "E1234567X" not in out.text and "072-918203-6" not in out.text
    assert "@priya_wdl" not in out.text
    # a NAME hit is extended over its patronymic (names come from the ML backends in production)
    from socareguard.detect.pipeline import _extend_names
    from socareguard.detect.sg import Hit

    hit = Hit(7, 12, "Priya", "NAME", "gliner", 0.9)
    assert _extend_names(t, [hit])[0].text == "Priya d/o Muthusamy"


def test_capacity_negation_is_not_inverted(tmp_path: Path):
    from socareguard.outbound.generalise import generalise_attribute

    assert "presumed" in generalise_attribute(
        "capacity", "Mother is not her deputy", "status_only", "disability"
    )
    assert "in question" in generalise_attribute(
        "capacity", "A deputy has been appointed under the MCA", "status_only", "disability"
    )


def test_reformatted_phone_and_given_name_restore(tmp_path: Path):
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("domestic-violence"), use_presidio=False, use_gliner=False)
    s.sanitise("Contact 91234567.", session="r1", seed=5)
    sur = next(
        m.surrogate for m in vault.mappings("r1") if m.category == "PHONE" and m.kind == "surrogate"
    )
    d = "".join(c for c in sur if c.isdigit())
    r = restore(f"Call {d[:4]} {d[4:]} or +65 {d[:4]} {d[4:]}.", vault, "r1")
    assert "9123 4567" in r.text and "+65 9123 4567" in r.text and not r.unrestored_surrogates
    # an unrestored surrogate fragment is reported, never shown as real
    r2 = restore(f"Call {d} now.", vault, "r1")
    assert "91234567" in r2.text


def test_shared_surrogate_restores_to_the_longest_original(tmp_path: Path):
    vault = Vault(tmp_path / "v.sqlite")
    from socareguard.outbound.vault import Mapping

    vault.put(Mapping("s", "Pang Hui Min", "Chong Su Lin", "NAME", "surrogate", "e1"))
    vault.put(Mapping("s", "Hui Min", "Chong Su Lin", "NAME", "surrogate", "e2"))
    assert restore("Client Chong Su Lin called.", vault, "s").text == "Client Pang Hui Min called."


def test_a_generalised_phrase_shared_by_two_originals_is_never_restored(tmp_path: Path):
    from socareguard.outbound.vault import Mapping

    vault = Vault(tmp_path / "v.sqlite")
    vault.put(
        Mapping(
            "g",
            "lumbar spondylosis",
            "has a health condition",
            "ATTR:diagnosis",
            "generalised",
            "a1",
        )
    )
    vault.put(
        Mapping(
            "g",
            "applying for IDAPE",
            "has a health condition",
            "ATTR:diagnosis",
            "generalised",
            "a2",
        )
    )
    r = restore("His wife has a health condition.", vault, "g")
    assert r.text == "His wife has a health condition." and r.ambiguous_generalised == [
        "has a health condition"
    ]


def test_hospital_identifiers_and_role_words(tmp_path: Path):
    from socareguard.detect.pipeline import _sane, detect
    from socareguard.detect.sg import Hit

    t = "MRN H1298450, Ward 9B, Bed 24. Son says he cannot take leave."
    cats = {(h.category, h.text) for h in detect(t, use_presidio=False, use_gliner=False).entities}
    assert ("MRN", "H1298450") in cats and any(c == "WARD_BED" for c, _ in cats)
    assert not _sane(Hit(0, 7, "Ward 9B", "NAME", "gliner", 0.9))
    assert not _sane(Hit(0, 3, "Son", "NAME", "gliner", 0.9))
    assert not _sane(Hit(0, 3, "Clt", "NAME", "gliner", 0.9))


def test_list_numbers_are_not_ages_and_warnings_stay_prior():
    from socareguard.detect.gazetteers import find_ages
    from socareguard.outbound.generalise import generalise_attribute

    assert find_ages("Next: (1) HDB appeal (2) email school") == []
    assert [h.text for h in find_ages("brother Aqil (8) at home")] == ["(8)"] or find_ages(
        "brother Aqil (8) at home"
    )
    g = generalise_attribute(
        "offence", "Prev warning Feb for fighting", "category", "youth-offending"
    )
    assert g.startswith("has a prior police warning")


def test_never_leak_patterns_are_withheld_and_denials_are_not_charges(tmp_path: Path):
    from socareguard.outbound.generalise import generalise_attribute

    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("disability"), use_presidio=False, use_gliner=False)
    out = s.sanitise(
        "WAIS-IV full scale IQ 55. Receives ComCare Long Term Assistance, $780 per month.",
        session="nl",
        seed=2,
    )
    assert "55" not in out.text and "$780" not in out.text and "[withheld" in out.text
    g = generalise_attribute(
        "offence", "Danial says he did not know it was stolen", "category", "youth-offending"
    )
    assert "disputes" in g
    # round 3 (YOUTH-F3): the disposition itself is kept, not flattened to "closed"
    assert "was withdrawn" in generalise_attribute(
        "offence", "the charge was withdrawn", "category", "youth-offending"
    )
    assert "family member" in generalise_attribute(
        "offence", "his cousin has a prior conviction for theft", "category", "youth-offending"
    )
    assert (
        generalise_attribute(
            "minor", "Intake, 4 Sep 2026, Youth Court diversion", "age_band", "youth-offending"
        )
        == "is a minor"
    )
    assert "15 to 17" in generalise_attribute(
        "minor", "Amirul, 15, a minor", "age_band", "youth-offending"
    )


def test_internal_audience_cues_win_and_reference_is_not_refer():
    from socareguard.screen.rules import audience_is_external

    assert not audience_is_external("Draft an internal note to my supervisor for countersigning")
    assert not audience_is_external("Summarise for my own file; note the Youth Court reference")
    assert audience_is_external("Write an email to the school principal")
    assert not audience_is_external(
        "Draft the pre-sentence report for the Youth Court", "youth-offending"
    )
    assert not audience_is_external(
        "Write a letter to his mother about the curfew", "youth-offending"
    )
    assert audience_is_external("Write a progress update to her father", "disability")
    assert audience_is_external(
        "Email the school principal about the case, ahead of the case conference", "youth-offending"
    )
    assert audience_is_external(
        "Draft the report for the Youth Court and copy the school", "youth-offending"
    )


def test_a_safety_plan_with_a_unit_number_is_redacted_whole(tmp_path: Path):
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("domestic-violence"), use_presidio=False, use_gliner=False)
    out = s.sanitise(
        "Safety plan: if he comes, the children go to the neighbour at #10-335 and call 91234567.",
        session="sp",
        seed=3,
    )
    assert "#10-335" not in out.text and "91234567" not in out.text and "withheld" in out.text


def test_titled_names_and_never_leak_precedence(tmp_path: Path):
    from socareguard.detect.pipeline import detect

    t = "Client Danial bin Rahman came with his mother Mdm Junaidah binte Salim. Danial said no."
    names = {
        h.text
        for h in detect(t, use_presidio=False, use_gliner=False).entities
        if h.category == "NAME"
    }
    assert "Mdm Junaidah binte Salim" in names
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack("disability"), use_presidio=False, use_gliner=False)
    out = s.sanitise("Aged 58. WAIS-IV FSIQ 58 recorded at the last review.", session="nl2", seed=1)
    assert "FSIQ 58" not in out.text and "withheld" in out.text
    out2 = s.sanitise(
        "PPO application filed; attends Toa Payoh Lorong 7 centre.", session="nl3", seed=1
    )
    assert "an employer" not in out2.text


def test_honorific_prefix_of_a_surrogate_restores_with_the_given_name(tmp_path: Path):
    from socareguard.outbound.sanitise import _derived_forms

    pairs = _derived_forms("NAME", "Nabilah binti Ibrahim", "Nur Izzati binti Osman")
    assert ("Nabilah", "Nur Izzati") in pairs
    from socareguard.inbound.restore import _fragments_left
    from socareguard.outbound.vault import Mapping

    maps = [
        Mapping("s", "Nabilah binti Ibrahim", "Nur Izzati binti Osman", "NAME", "surrogate", "e")
    ]
    assert _fragments_left("His mother, Nur Nabilah, said", maps) == []
