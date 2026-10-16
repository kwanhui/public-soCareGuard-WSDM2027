"""Round 3 of the second review set (2026-09-28): outbound defects on the reviewers' own notes.

Each test runs the reviewer's note with the NER hits recorded on it (tests/recorded_round3.py), so
the spans are the ones the reviewer's run produced."""

import re
from pathlib import Path

from socareguard.inbound.restore import restore
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import available_packs, load_pack
from socareguard.proxy.core import _sanitise_message
from tests import recorded_round3 as rec


def _out(monkeypatch, tmp_path: Path, name: str, pack: str | None = None, **kw):
    note = rec.use(monkeypatch, name)
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack(pack or note["pack"]), **kw)
    return _sanitise_message(s, note["text"], name, 7, 1), vault


def _names(res) -> set[str]:
    return {h.text for h, _, kind in res.replacements if h.category == "NAME"}


# YOUTH-F1: a Malay kin phrase read as a person, given an invented Chinese name.


def test_malay_kin_phrase_is_kept_and_no_name_is_invented(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "youth_malay")
    # every surrogate name stands for a person the note names, one to one
    # (round 4: the client's given name before the offence clause is its own span, a short form
    # of the same person that takes the given name of the same surrogate)
    assert _names(res) == {"Ahmad Danish bin Yusof", "Ahmad", "Zainab binte Osman"}, (
        res.replacements
    )
    assert "Mak dia, " in res.text, res.text
    surrogates = {new for h, new, _ in res.replacements if h.category == "NAME"}
    short = {new for h, new, _ in res.replacements if h.text == "Ahmad"}
    assert len(surrogates - short) == 2, surrogates
    assert all(any(s in full.split() for full in surrogates - short) for s in short), surrogates
    # the only capitalised two-word names in the payload are those surrogates
    assert "Zainab" not in res.text and "Ahmad Danish" not in res.text, res.text


def test_lower_case_words_at_a_name_edge_are_trimmed(tmp_path):
    from socareguard.detect.pipeline import _resolve
    from socareguard.detect.sg import Hit

    got = _resolve(
        [
            Hit(0, 7, "Mak dia", "NAME", "presidio.PERSON", 0.85),
            Hit(9, 19, "Ahmad kena", "NAME", "presidio.PERSON", 0.85),
            Hit(21, 29, "Rajesh s", "NAME", "presidio.PERSON", 0.85),
            Hit(31, 36, "Ah Ma", "NAME", "presidio.PERSON", 0.85),
        ]
    )
    assert [h.text for h in got] == ["Ahmad", "Rajesh"], got


def test_english_kin_phrase_is_never_a_name(tmp_path):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("youth-offending"),
        use_presidio=False,
        use_gliner=False,
    )
    out = s.sanitise("His mother, Mdm Zainab binte Osman, attends every session.", "k", seed=1)
    assert out.text.startswith("His mother, Mdm "), out.text
    assert "Zainab" not in out.text


# COACH-F1: medication and dose, and a prescriber's title.


def test_medication_and_dose_are_withheld_and_prescriber_keeps_title(monkeypatch, tmp_path):
    res, vault = _out(monkeypatch, tmp_path, "coach_medication")
    out = res.text
    assert "Risperidone" not in out and "2mg" not in out, out
    assert "Takes [medication withheld], prescribed by Dr " in out, out
    assert "Amanda" not in out and "Wong" not in out, out
    # the employer's name does not cross in pieces around a generalised estate
    assert "Ace Hardware" not in out, out
    # a public hospital is a public body, not "an employer"
    assert "psychiatrist at the Institute of Mental Health" in out, out
    # a reply that writes the titled surrogate restores to one title, not "Dr Dr"
    dr = next(new for h, new, _ in res.replacements if h.text == "Dr Amanda Wong")
    assert dr.startswith("Dr "), dr
    back = restore(f"prescribed by {dr}, and {dr} agrees.", vault, "coach_medication").text
    assert back == "prescribed by Dr Amanda Wong, and Dr Amanda Wong agrees.", back


def test_medication_pattern_in_every_pack(tmp_path):
    notes = {
        "He is on sertraline 50 mg daily and sleeps well.": "sertraline",
        "She was prescribed Epilim last month.": "Epilim",
        "On Seroquel XR 300mg nocte since June.": "Seroquel",
    }
    for pack in available_packs():
        s = Sanitiser(
            Vault(tmp_path / f"{pack}.sqlite"),
            load_pack(pack),
            use_presidio=False,
            use_gliner=False,
        )
        for i, (note, drug) in enumerate(notes.items()):
            out = s.sanitise(note, f"{pack}-{i}", seed=1).text
            assert drug not in out and "[medication withheld]" in out, (pack, out)
    # plain amounts, counts and "prescribed by" are left alone
    s = Sanitiser(
        Vault(tmp_path / "x.sqlite"), load_pack("disability"), use_presidio=False, use_gliner=False
    )
    for note in (
        "He has completed 40 of 60 hours.",
        "Stable on medication; dose to be reviewed.",
        "Seen by the doctor who prescribed it.",
    ):
        assert "withheld" not in s.sanitise(note, "plain", seed=1).text, note


def test_titled_clinician_is_one_person_across_forms(tmp_path):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"), load_pack("disability"), use_presidio=False, use_gliner=False
    )
    out = s.sanitise("Reviewed by Prof Lee Kah Wai. Prof Lee will see him again.", "p", seed=3)
    m = re.match(r"Reviewed by (Prof [A-Z][a-z]+)", out.text)
    assert m, out.text
    assert "Lee" not in out.text and "Kah Wai" not in out.text, out.text


# YOUTH-F3: a charge withdrawn on CCTV evidence left as "an allegation the client disputes".


def test_withdrawn_charge_keeps_its_disposition_and_basis(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "youth_withdrawn")
    out = res.text
    # round 4 (PROB-F2, FSC-N2): the clause names the client, so the offence is replaced in place
    # and the name (substituted), the date and the basis stay with the charge
    assert re.search(
        r"The charge of a property offence against [A-Z][a-z]+ was withdrawn by the prosecution on"
        r" 15 Aug 2026 after CCTV footage showed she was not involved; the case was closed with no"
        r" further action\.",
        out,
    ), out
    assert "Aisyah" not in out, out
    assert "disputes" not in out and "allegation" not in out, out
    # the plain denial sentence is kept as a denial
    assert "has consistently denied any involvement from the start." in out, out


# YOUTH-F4: a named gang crossed as written; a Chinese name took a surrogate of the other gender.


def test_named_group_is_withheld_and_surrogate_follows_pronouns(monkeypatch, tmp_path):
    from socareguard.outbound.surrogates import gender_evidence

    res, _ = _out(monkeypatch, tmp_path, "youth_gang")
    out = res.text
    assert "18 Tigers" not in out and "linked to a group called [affiliation withheld]." in out, out
    # the offence clause the withheld name cut is still generalised, with its estate
    assert "shop theft" not in out and "Hougang" not in out, out
    assert "arrested for a property offence in the north-east" in out, out
    sur = next(new for h, new, _ in res.replacements if h.text == "Kai Ming Ong")
    assert gender_evidence(sur) == "male", sur


def test_affiliation_pattern_forms(tmp_path):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("youth-offending"),
        use_presidio=False,
        use_gliner=False,
    )
    for note, name in (
        ("He was seen with the Ang Soon Tong gang last week.", "Ang Soon Tong"),
        ("A crew known as Salakau 369 recruits at the mall.", "Salakau"),
    ):
        out = s.sanitise(note, "aff", seed=1).text
        assert name not in out and "[affiliation withheld]" in out, out
    for note in ("A gang member approached him.", "He wants to leave the group."):
        assert "withheld" not in s.sanitise(note, "aff2", seed=1).text, note


def test_pronouns_give_the_gender_for_chinese_and_indian_names():
    from socareguard.outbound.surrogates import SurrogateFactory, gender_from_pronouns, guess_origin

    text = (
        "Client: Yi Ling Koh, 15. Yi Ling says he wants to change school. "
        "Referred with Kavya Nair, 16; she attends the same class. "
        "Zhi Xuan Goh came too. His mother said she would call."
    )
    spans = []
    for n in ("Yi Ling Koh", "Yi Ling", "Kavya Nair", "Zhi Xuan Goh"):
        i = text.index(n)
        spans.append((i, i + len(n), n))
    got = gender_from_pronouns(text, spans)
    assert got["Yi Ling Koh"] == "male" and got["Yi Ling"] == "male", got
    assert got["Kavya Nair"] == "female", got
    # "His mother said she": "she" is the mother; "His" alone is Zhi Xuan's
    assert got["Zhi Xuan Goh"] == "male", got
    assert guess_origin("Kavya Nair") == "indian"
    f = SurrogateFactory(1)
    assert guess_origin(f.name("Kavya Nair", gender_hint="female")) == "indian"


# YOUTH-W1: generic role phrases became invented company names.


def test_generic_employer_phrases_stay_as_written(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "youth_spent")
    out = res.text
    assert "Write a letter to a prospective employer supporting" in out, out
    assert "warehouse assistant role at a logistics company." in out, out
    from socareguard.outbound.surrogates import _ORG_STEMS

    assert not any(stem in out for stem in _ORG_STEMS), out
    # a named organisation still takes a surrogate under the youth pack
    s = Sanitiser(
        Vault(tmp_path / "w.sqlite"),
        load_pack("youth-offending"),
        use_presidio=False,
        use_gliner=False,
    )
    named = s.sanitise("He works part-time at Kestrel Tan Holdings.", "w", seed=1)
    assert "Kestrel Tan Holdings" not in named.text, named.text


# WSDM N7: "No PPO yet" neutralised; "(6, school)" not banded.


def test_wsdm_note_keeps_the_negative_order_status_and_bands_the_age(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "wsdm_dv")
    out = res.text
    assert "No protection order is on record; she is not ready to apply." in out, out
    assert "status recorded" not in out and "is in place" not in out, out
    assert re.search(r"\(6 to 8, a primary school\)", out), out
    assert "Sengkang" not in out and "Kaiden" not in out, out


# COACH-F2: the employer's name never came back, even in an internal handover.


def _guard(tmp_path: Path):
    from socareguard.ledger import Ledger
    from socareguard.proxy.core import Guard

    return Guard(
        vault=Vault(tmp_path / "g.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=True,
        use_gliner=True,
    )


def test_employer_is_a_reversible_surrogate_for_an_internal_audience(monkeypatch, tmp_path):
    note = rec.use(monkeypatch, "coach_handover")
    g = _guard(tmp_path)
    msgs = [{"role": "user", "content": note["text"]}]
    # the coach set the audience to internal with the header (round-3 note COACH-6)
    for audience in ("internal",):
        session = f"handover-{audience}"
        res = g.run(
            msgs,
            "disability",
            "openai/gpt-4.1-mini",
            session=session,
            reply_fixture="",
            seed=7,
            audience=audience,
        )
        sent = res.outbound_messages[0]["content"]
        assert "Kopi Corner Cafe" not in sent, sent
        sur = next(r["outbound"] for r in res.replacements if r["original"] == "Kopi Corner Cafe")
        assert sur != "an employer" and sur in sent, sur
        assert res.ledger_row["employer_treatment"].startswith("surrogate, restored"), (
            res.ledger_row
        )
        back = restore(f"Her trial shift at {sur} starts on 22 Sep.", g.vault, session).text
        assert back == "Her trial shift at Kopi Corner Cafe starts on 22 Sep.", back


def test_employer_is_generalised_for_an_external_audience(monkeypatch, tmp_path):
    note = rec.use(monkeypatch, "coach_handover")
    g = _guard(tmp_path)
    res = g.run(
        [{"role": "user", "content": note["text"]}],
        "disability",
        "openai/gpt-4.1-mini",
        session="handover-ext",
        reply_fixture="",
        seed=7,
        audience="external",
    )
    sent = res.outbound_messages[0]["content"]
    assert "trial shift at an employer," in sent and "Kopi Corner" not in sent, sent
    assert res.ledger_row["employer_treatment"].startswith("generalised to its kind"), (
        res.ledger_row
    )
    # the default Sanitiser (the evaluation runs) behaves as external
    s = Sanitiser(Vault(tmp_path / "d.sqlite"), load_pack("disability"))
    assert s.audience is None


def test_employer_treatment_follows_the_audience_the_instruction_implies(tmp_path):
    from socareguard.ledger import Ledger
    from socareguard.proxy.core import Guard

    g = Guard(
        vault=Vault(tmp_path / "a.sqlite"),
        ledger=Ledger(tmp_path / "a.jsonl"),
        use_presidio=False,
        use_gliner=False,
    )
    body = "\n\nPlan: trial shift at Kopi Corner Pte Ltd next week."
    for instruction, want in (
        ("Summarise this for my own case file.", "surrogate, restored"),
        ("Draft an email to the cafe manager introducing her.", "generalised to its kind"),
    ):
        res = g.run(
            [{"role": "user", "content": instruction + body}],
            "disability",
            "openai/gpt-4.1-mini",
            session=instruction[:8],
            reply_fixture="",
            seed=1,
        )
        assert "Kopi Corner" not in res.outbound_messages[0]["content"]
        assert res.ledger_row["employer_treatment"].startswith(want), res.ledger_row


def test_capitalised_name_particles_are_kept_and_agency_acronyms_are_not_names():
    from socareguard.detect.pipeline import _resolve
    from socareguard.detect.sg import Hit

    got = _resolve(
        [
            Hit(0, 9, "Ho Jia Le", "NAME", "presidio.PERSON", 0.85),
            Hit(11, 22, "Ahmad bin", "NAME", "presidio.PERSON", 0.85),
            Hit(24, 31, "MOE SSO", "NAME", "presidio.PERSON", 0.85),
            Hit(33, 59, "Saya takut kalau dia terus", "NAME", "presidio.PERSON", 0.85),
        ]
    )
    assert [h.text for h in got] == ["Ho Jia Le", "Ahmad"], got
