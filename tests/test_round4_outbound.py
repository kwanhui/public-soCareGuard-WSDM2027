"""Round 4 of the second review set (2026-09-28): outbound defects on the reviewers' own notes.

Each test runs the reviewer's note with the NER hits recorded on it (tests/recorded_round4.py), so
the spans are the ones the reviewer's run saw."""

import re
from pathlib import Path

import pytest

from socareguard.outbound.generalise import generalise_attribute
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack
from socareguard.proxy.core import _sanitise_message
from tests import recorded_round4 as rec


def _out(monkeypatch, tmp_path: Path, name: str, pack: str | None = None, audience="internal"):
    note = rec.use(monkeypatch, name)
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack(pack or note["pack"]), audience=audience)
    return _sanitise_message(s, note["text"], name, 7, 1), note


def _surrogates(res) -> dict[str, str]:
    return {h.text: new for h, new, kind in res.replacements if kind == "surrogate"}


# FSC-N1: the diagnosis rule matched the practitioner's "Plan:" sentence and deleted it.


@pytest.mark.parametrize("pack", ["disability", "domestic-violence"])
def test_plan_sentence_survives_verbatim(monkeypatch, tmp_path, pack):
    res, _ = _out(monkeypatch, tmp_path, "fsc_plan", pack=pack)
    out = res.text
    assert out.endswith(
        "\n\nPlan: continue psychiatric follow-up, monitor medication compliance, refer for"
        " counselling."
    ), out
    # the diagnosis sentence is still generalised, once
    assert "major depressive disorder" not in out and "sertraline" not in out, out
    assert out.count("psychiatric condition") == 1, out


@pytest.mark.parametrize(
    "key,text,before",
    [
        ("diagnosis", "Plan: refer to IMH for review of his schizophrenia medication", ""),
        ("diagnosis", "Assessment: depression is stable on current medication", "Seen today. "),
        ("offence", "Next steps: follow up with the IO on the theft charge", ""),
        ("diagnosis", "I will refer her for a psychiatric assessment", "Seen today. "),
        ("offence", "The worker will attend the mention on the shop theft charge", ""),
        ("diagnosis", "Impression: mood low, medication compliance uncertain", "\n"),
    ],
)
def test_practitioner_sentence_keeps_its_wording(key, text, before):
    pack = "youth-offending" if key == "offence" else "disability"
    got = generalise_attribute(key, text, "category", pack, before=before)
    # the sentence keeps its opening and its verbs; only a phrase naming the condition may change
    assert got.split()[0] == text.split()[0], got
    assert not got.lower().startswith(("has ", "is the subject")), got
    for word in ("refer", "follow up", "attend", "compliance", "stable"):
        if word in text:
            assert word in got, got


# PROB-F2, PROB-F3, FSC-N2: charges keep their status and date, one clause per charge, never a
# bare fragment, and never at the cost of the person's name.


def test_two_charges_keep_their_outcomes_dates_and_conjunction(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "prob_youthcourt", audience="external")
    out = res.text
    assert "shop theft" not in out and "unlawful assembly" not in out, out
    assert (
        "He was charged with two offences: a property offence on 10 Jan 2026, which he admitted and"
        " for which the probation order was made, and a separate charge of a public order offence"
        " on 2 Feb 2026, which was withdrawn by the prosecution on 20 Mar 2026 for insufficient"
        " evidence." in out
    ), out


def test_pending_charge_survives_and_no_fragment_appears(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "prob_pending")
    out = res.text
    assert out.endswith(
        "the two accounts differ. The second charge is pending before the Youth Court."
    ), out
    assert "Is a minor" not in out and "is the subject of a current matter" not in out, out
    assert "Two charges: first, a property offence on 3 Aug 2026, admitted" in out, out
    assert re.search(
        r"Second, a property offence on 10 Aug 2026, which [A-Z][a-z]+ denies;", out
    ), out
    assert "trespass" not in out and "shop theft" not in out and "Daniel" not in out, out


def test_short_note_keeps_the_clients_name(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "fsc_mall")
    out = res.text
    sub = _surrogates(res)
    assert "Aisha Lim" in sub and "Aisha" not in out, res.replacements
    assert f"Client {sub['Aisha Lim']}, 14, " in out, out
    # the matter is stated with its date, as the rest of the sentence about the client
    assert "is the subject of a current matter: a property offence on 26 Sep 2026." in out, out
    assert "shoplifting" not in out and "Jurong Point" not in out, out
    assert not re.search(r"(?:^|\n)Is the subject", out), out


def test_first_time_catch_is_a_current_matter_with_no_prior_record(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "prob_singlish")
    out = res.text
    assert re.search(
        r"Client [A-Z][a-z]+(?: [A-Z][a-z]+)+ is the subject of a current matter: a property offence"
        r" on 12 Sep 2026; no prior offence record is noted\.",
        out,
    ), out


@pytest.mark.parametrize(
    "text,must",
    [
        (
            "and the second charge, where he was caught vaping, was withdrawn on 20 Mar 2026",
            "and a charge of a tobacco or vaping matter was withdrawn on 20 Mar 2026",
        ),
        (
            (
                "the charge of voluntarily causing hurt, where he was caught fighting, is pending"
                " before the Youth Court, fixed for mention on 3 Oct"
            ),
            (
                "a charge of an offence involving violence is pending before the Youth Court, fixed"
                " for mention on 3 Oct"
            ),
        ),
    ],
)
def test_charge_statement_keeps_status_date_and_conjunction(text, must):
    got = generalise_attribute("offence", text, "category", "youth-offending")
    assert got == must, got


# PROB-F4 and the carried "Blk 834 the east Street 2": the estate rule never applies inside an
# address; the address surrogate covers the whole address.


def test_estate_inside_a_street_name_is_part_of_the_address(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "prob_singlish")
    out = res.text
    assert "Sengkang" not in out and "East Way" not in out and "the north-east" not in out, out
    assert re.search(r"He stay at Blk \d+[A-Z]? [A-Z][A-Za-z ]+?(?: \d+)?, studying at", out), out
    addr = [h.text for h, _, _ in res.replacements if h.category == "ADDRESS"]
    assert addr == ["Blk 203 Sengkang East Way"], addr


@pytest.mark.parametrize(
    "address,street_words",
    [
        ("Blk 834 Tampines Street 2", ["Tampines", "Street 2"]),
        ("Blk 450 Hougang Avenue 3", ["Hougang", "Avenue 3"]),
        ("Blk 203 Sengkang East Way", ["Sengkang", "East Way"]),
        ("Blk 45 Bedok North Drive", ["Bedok", "North Drive"]),
        ("Blk 12 Jalan Bukit Merah", ["Bukit Merah", "Jalan"]),
        ("Blk 88 Bedok North Street 4 #05-123, Singapore 460088", ["Bedok", "460088"]),
    ],
)
def test_street_forms_leave_as_one_address_surrogate(tmp_path, address, street_words):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("domestic-violence"),
        use_presidio=False,
        use_gliner=False,
    )
    out = s.sanitise(f"She moved to {address} last month with the children.", "k", seed=3)
    for w in street_words:
        assert w not in out.text, out.text
    assert not re.search(r"the (?:east|west|north|north-east|central area) [A-Z]", out.text), (
        out.text
    )
    m = re.fullmatch(r"She moved to (Blk \d+[A-Z]? .+?) last month with the children\.", out.text)
    assert m, out.text
    # the surrogate has the parts the original has
    assert ("#" in m.group(1)) == ("#" in address) and ("Singapore" in m.group(1)) == (
        "Singapore" in address
    ), m.group(1)


# DV-N1: the workplace pattern swallowed the next clause, a safety instruction included.


def test_workplace_withholding_stops_at_the_workplace(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "dv_workplace")
    out = res.text
    assert "Uniqlo" not in out and "Bugis" not in out, out
    assert re.search(
        r"She has started a new job as a retail assistant at \[workplace withheld\] and asked that"
        r" this not be mentioned to [A-Z][a-z]+ if he calls the centre\.",
        out,
    ), out


@pytest.mark.parametrize(
    "sentence,kept",
    [
        ("She works at Giant Hypermarket, not at the old place.", ", not at the old place."),
        ("She works at Sheng Siong Bedok never on weekends.", " never on weekends."),
        ("She works at Kopi Corner but don't tell her brother.", " but don't tell her brother."),
        ("He works at a logistics company do not share this.", " do not share this."),
    ],
)
def test_workplace_pattern_is_bounded_to_the_noun_phrase(tmp_path, sentence, kept):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("domestic-violence"),
        use_presidio=False,
        use_gliner=False,
    )
    out = s.sanitise(sentence, "k", seed=3).text
    assert "[workplace withheld]" in out and out.endswith(kept), out


# WSDM-N4, PROB-F5, FSC-N4b: a possessive is the same person; common Singapore nouns are never
# names or employers; public bodies are never employers; malls and shared places are places.


def test_possessive_takes_the_same_surrogate_and_kopitiam_is_not_a_person(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "wsdm_intake", audience="external")
    out = res.text
    sub = _surrogates(res)
    assert "Wei Ming's" not in sub, sub
    wm = sub["Wei Ming"]
    assert f"{wm}'s brother, " in out, out
    assert "Kopitiam" not in sub and "Kopitiam" in out, sub
    assert f"retrenched from {sub['Ah Ming']}'s Kopitiam in Aug" in out, out
    # four people are named in the payload, not five: the client, his mother, son and brother
    people = {v for k, v in sub.items() if k in {"TAN WEI MING", "Wei Ming", "Tan"}}
    assert len({p.split()[0] for p in people}) == 1, people


@pytest.mark.parametrize(
    "sentence,kept",
    [
        (
            "She was referred to the Housing Development Board for a rental flat.",
            "Housing Development Board",
        ),
        ("He works as a cleaner at HDB.", "HDB"),
        ("His CPF Board statement shows the balance.", "CPF Board"),
        ("MSF has approved the grant.", "MSF"),
        ("They met at the kopitiam near the void deck.", "kopitiam"),
    ],
)
def test_public_bodies_and_common_nouns_are_kept(tmp_path, sentence, kept):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("disability"),
        use_presidio=False,
        use_gliner=False,
        audience="internal",
    )
    out = s.sanitise(sentence, "k", seed=3)
    assert kept in out.text, out.text
    assert not any(h.text == kept and k == "surrogate" for h, _, k in out.replacements)


def test_hdb_in_the_transfer_note_is_not_an_invented_employer(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "fsc_transfer")
    out = res.text
    assert "a referral to the Housing Development Board for a possible larger unit" in out, out
    assert not re.search(r"(?:Services|Centre) for a possible larger unit", out), out


def test_mall_is_a_place_not_a_company(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "prob_singlish")
    assert not any(h.text == "Compass One" and k == "surrogate" for h, _, k in res.replacements), (
        res.replacements
    )
    assert "Compass One" not in res.text
    s = Sanitiser(
        Vault(tmp_path / "w.sqlite"),
        load_pack("youth-offending"),
        use_presidio=False,
        use_gliner=False,
        audience="internal",
    )
    out = s.sanitise("He was seen at Tampines Mall and later at Jurong Point.", "k", seed=3).text
    assert out == "He was seen at a shopping mall and later at a shopping mall.", out


# WSDM-N1: a spaced NRIC left the premises verbatim beside its compact form.


def test_spaced_nric_is_substituted(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "wsdm_intake", audience="external")
    out = res.text
    assert "S 1234567 D" not in out and "1234567" not in out, out
    nrics = [h.text for h, _, k in res.replacements if h.category == "NRIC" and k == "surrogate"]
    assert {"s1234567d", "S 1234567 D", "S5012345Z"} <= set(nrics), nrics


def _variants() -> list[dict]:
    import json

    path = Path(__file__).parent / "data" / "nric-variants.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.mark.parametrize("row", _variants(), ids=lambda r: r["id"])
def test_nric_format_variant_is_detected_and_never_leaves(tmp_path, row):
    from socareguard.detect.sg import find_nric

    hits = [(h.start, h.end) for h in find_nric(row["text"])]
    assert (row["start"], row["end"]) in hits, (row["text"], hits)
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("disability"),
        use_presidio=False,
        use_gliner=False,
    )
    out = s.sanitise(row["text"], "k", seed=1).text
    assert row["variant"] not in out and row["canonical"][1:8] not in out, out


def test_variants_command_reports_recall(tmp_path, monkeypatch):
    import json

    from socareguard.eval import run_detect

    monkeypatch.setattr(run_detect, "OUT", tmp_path)
    monkeypatch.chdir(Path(__file__).parent.parent)
    res = run_detect.run_variants(use_presidio=False, use_gliner=False)
    assert res["variants"] == 30 and res["recall_covered"] == 1.0 and res["leaked"] == 0, res
    assert json.loads((tmp_path / "nric-variants.json").read_text())["variants"] == 30


# FSC-N4a: a helper's work permit number was labelled PASSPORT in the replacement table.


def test_work_permit_is_its_own_category(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "fsc_permit")
    wp = [(h.category, h.text, new) for h, new, k in res.replacements if "1234567" in h.text]
    assert len(wp) == 1 and wp[0][0] == "WORK_PERMIT" and wp[0][1] == "G1234567N", wp
    assert re.fullmatch(r"[FGM]\d{7}[A-Z]", wp[0][2]), wp
    assert "G1234567N" not in res.text and f"work permit number {wp[0][2]}," in res.text, res.text


# FSC-N3: a colloquial name outside the given-name lists took a female surrogate for a man.


def test_colloquial_name_takes_its_gender_from_the_pronouns(monkeypatch, tmp_path):
    from socareguard.outbound.surrogates import gender_evidence

    res, _ = _out(monkeypatch, tmp_path, "fsc_ahbeng")
    new = _surrogates(res)["Lim Ah Beng"]
    assert gender_evidence(new) == "male", new


def test_pronoun_past_a_named_relative_of_the_other_gender_counts():
    from socareguard.outbound.surrogates import gender_from_pronouns

    t = "Client: Tan Ah Kow, 70. Wife said he is not eating. Daughter said she visits."
    i = t.index("Tan Ah Kow")
    assert gender_from_pronouns(t, [(i, i + 10, "Tan Ah Kow")]) == {"Tan Ah Kow": "male"}
    # a pronoun that could be the relative's own is still skipped
    t2 = "Client: Tan Ah Kow, 70. Wife said she is tired."
    assert gender_from_pronouns(t2, [(i, i + 10, "Tan Ah Kow")]) == {}


# FSC-N1, the general guard: no rule restates a plan. The capacity and minor rules replaced plan
# items ("1) Arrange formal capacity assessment ...") with "Capacity for this decision: see record".


@pytest.mark.parametrize(
    "key,rule,text,before",
    [
        (
            "capacity",
            "status_only",
            "1) Arrange formal capacity assessment by psychiatrist and OT",
            "Actions and plan:\n",
        ),
        ("capacity", "status_only", "I will refer client for formal capacity assessment", "Seen. "),
        (
            "capacity",
            "status_only",
            "Refer for formal capacity assessment and OT home assessment",
            "",
        ),
        ("minor", "age_band", "Plan: explain the Youth Court mention process to the family", ""),
    ],
)
def test_plan_items_are_never_restated(key, rule, text, before):
    pack = "youth-offending" if key == "minor" else "disability"
    assert generalise_attribute(key, text, rule, pack, before=before) == text


def test_a_capacity_finding_is_still_generalised():
    got = generalise_attribute(
        "capacity", "She lacks capacity to manage her finances", "status_only", "disability"
    )
    # the finding keeps the decision it concerns (round 5, DCM-F2)
    assert got == "lacks capacity for financial and property decisions", got


def test_a_name_before_a_non_predicate_statement_keeps_the_clause(tmp_path):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("youth-offending"),
        use_presidio=False,
        use_gliner=False,
    )
    out = s.sanitise("Seen today. Mr Oliver Tan has no prior record with the police.", "k", seed=3)
    assert "no prior offence record is noted" not in out.text or not re.search(
        r"Mr [A-Z][a-z]+ no prior", out.text
    ), out.text
    assert "Oliver" not in out.text, out.text
