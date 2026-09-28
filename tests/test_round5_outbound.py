"""Round 5 of the second review set (2026-09-28): outbound defects on the reviewers' own notes.

Each test runs the reviewer's note with the NER hits recorded on it (tests/recorded_round5.py), so
the spans are the ones the reviewer's run saw."""

import re
from pathlib import Path

import pytest

from socareguard.outbound.generalise import generalise_attribute
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack
from socareguard.proxy.core import _sanitise_message
from tests import recorded_round5 as rec


def _out(monkeypatch, tmp_path: Path, name: str, audience="internal"):
    note = rec.use(monkeypatch, name)
    vault = Vault(tmp_path / "v.sqlite")
    s = Sanitiser(vault, load_pack(note["pack"]), audience=audience)
    return _sanitise_message(s, note["text"], name, 7, 1), note


def _surrogates(res) -> dict[str, str]:
    return {h.text: new for h, new, kind in res.replacements if kind == "surrogate"}


# DCM-F1: "No capacity assessment has been done" tripped the "no capacity" branch, so the fact that
# no deputy or donee exists was deleted and the model wrote "his legal guardian".


def test_no_capacity_assessment_is_not_a_finding(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "dcm_consent")
    out = res.text
    assert "in question" not in out, out
    assert "No capacity assessment has been done" in out, out
    assert "no deputy or donee is appointed" in out, out
    # the proxy consent is kept as a predicate the model and the judge can read
    assert "consent was given by a caregiver without legal authority recorded" in out, out
    # the mother's signature on his behalf leaves as written, with her name substituted
    assert "signed the consent form on his behalf" in out, out


@pytest.mark.parametrize(
    "text,must,must_not",
    [
        ("No capacity assessment has been done", "no capacity assessment", "in question"),
        ("capacity has not been assessed", "no capacity assessment", "in question"),
        ("He has no capacity to decide on his finances", "lacks capacity", "presumed"),
        ("no capacity assessment and no deputy appointed", "presumed", "in question"),
    ],
)
def test_no_assessment_and_no_capacity_stay_distinct(text, must, must_not):
    got = generalise_attribute("capacity", text, "status_only", "disability")
    assert must in got, got
    assert must_not not in got, got


def test_proxy_consent_predicate_needs_a_proxy_consent():
    note = "Client has autism. No deputy or donee has been appointed. He signed the form himself."
    got = generalise_attribute(
        "capacity", "No deputy or donee has been appointed", "status_only", "disability", note=note
    )
    assert got == "no deputy or donee is appointed; capacity is presumed", got


# DCM-F2: two decision-specific findings left as "this decision" twice, indistinguishable.


def test_capacity_findings_keep_their_decision(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "dcm_capacity")
    out = res.text
    assert "Has capacity for day-to-day decisions." in out, out
    assert "Lacks capacity for financial and property decisions." in out, out
    assert "No deputy or donee is appointed for financial and property decisions" in out, out
    # a lack of capacity found elsewhere in the note is never contradicted by "presumed"
    assert "presumed" not in out, out
    assert "this decision" not in out, out
    # the heading states no finding and keeps its wording, with the name substituted
    assert out.split("\n\n")[1].startswith("Capacity assessment for Mdm "), out
    assert "Noraini" not in out, out


@pytest.mark.parametrize(
    "text,want",
    [
        ("she has capacity to decide where she lives", "has capacity for decisions about where"),
        ("he lacks capacity to consent to surgery", "lacks capacity for healthcare decisions"),
        (
            "capacity to manage money is impaired",
            "capacity for financial and property decisions is",
        ),
        ("she has capacity to make this decision", "has capacity for this decision"),
    ],
)
def test_capacity_polarity_with_decision(text, want):
    got = generalise_attribute("capacity", text, "status_only", "disability")
    assert got.startswith(want), got


# The carried UC3 garble: "Capacity for this decision: see record, held them across the session".


def test_uc3_capacity_clause_has_no_fragment():
    text = (
        "Capacity: Priya understood the options when explained with pictures, held them across the"
        " session and gave reasons ('I like coffee, I want money')"
    )
    got = generalise_attribute("capacity", text, "status_only", "disability")
    assert got == "has capacity for this decision", got


# DCM-F4: a second diagnosis dropped; a caregiver's role rewritten as a health condition; the
# deputy's name lost even for the practitioner's own file, and "under" cut to "r".


def test_each_diagnosis_takes_its_category(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "dcm_careplan")
    out = res.text
    assert "Has a developmental disability and a neurological condition." in out, out
    assert "epilepsy" not in out and "intellectual" not in out, out


def test_a_caregivers_role_is_not_a_health_condition(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "dcm_careplan")
    out = res.text
    assert "who assists with daily living and medication reminders." in out, out
    assert "health condition" not in out, out


def test_deputy_name_is_restorable_for_an_internal_audience(monkeypatch, tmp_path):
    from socareguard.inbound.restore import restore

    res, _ = _out(monkeypatch, tmp_path, "dcm_careplan", audience="internal")
    out = res.text
    deputy = _surrogates(res)["Mr Tan Jun Wei"]
    assert (
        f"Her brother, {deputy}, has been appointed as her deputy for property and financial"
        " affairs by the Family Court under the Mental Capacity Act." in out
    ), out
    assert "Tan Jun Wei" not in out, out
    reply = f"Mr {deputy.split(' ', 1)[1]} is her deputy for financial affairs."
    back = restore(reply, Vault(tmp_path / "v.sqlite"), "dcm_careplan").text
    assert back == "Mr Tan Jun Wei is her deputy for financial affairs.", back


def test_deputy_is_withheld_whole_for_an_external_audience(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "dcm_careplan", audience="external")
    out = res.text
    assert "[withheld: deputyship or donee status; see record]. Plan:" in out, out
    assert "Tan Jun Wei" not in out and "deputy for property" not in out, out
    assert "]r the" not in out, out


@pytest.mark.parametrize(
    "sentence",
    [
        "Her son was appointed as her deputy by the Family Court under the Mental Capacity Act.",
        "The deputyship order names her nephew as deputy for property and affairs under the MCA.",
    ],
)
def test_deputyship_placeholder_never_cuts_a_word(tmp_path, sentence):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("disability"),
        use_presidio=False,
        use_gliner=False,
        audience="external",
    )
    out = s.sanitise(sentence, "w", seed=1).text
    assert "[withheld: deputyship or donee status; see record]" in out, out
    tail = out.split("]", 1)[1]
    assert tail in ("", "."), out


# DCM-F5: "his leg heals improves" in the restored draft.


def test_restore_drops_the_verb_the_original_supplies(tmp_path):
    from socareguard.inbound.restore import restore
    from socareguard.outbound.vault import Mapping

    v = Vault(tmp_path / "v.sqlite")
    v.put(Mapping("s", "leg heals", "health condition", "ATTR:disability", "generalised", "x"))
    v.put(Mapping("s", "warehouse job", "Bellmoor Services", "EMPLOYER", "surrogate", "y"))
    reply = (
        "He also conveyed a desire to return to Bellmoor Services once his health condition"
        " improves."
    )
    back = restore(reply, v, "s").text
    assert back == "He also conveyed a desire to return to warehouse job once his leg heals.", back


def test_prognosis_clause_keeps_its_verb_outbound(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "dcm_ownwords")
    assert res.text.endswith("once his health condition heals."), res.text


# DPO-F1: a URL that embeds the client's name left the premises verbatim.


def test_the_dpos_url_leaves_as_a_surrogate_link(monkeypatch, tmp_path):
    from socareguard.inbound.restore import restore

    res, _ = _out(monkeypatch, tmp_path, "dpo_url", audience="external")
    out = res.text
    assert "johnlim1998" not in out and "John Lim" not in out, out
    link = _surrogates(res)["https://facebook.com/johnlim1998"]
    assert re.fullmatch(r"https://facebook\.com/user\d{4,5}", link), link
    assert f"profile at {link} where he discusses" in out, out
    # the practitioner's draft gets the real link back, with or without the scheme
    vault = Vault(tmp_path / "v.sqlite")
    back = restore(f"See {link} and {link.split('//', 1)[1]}.", vault, "dpo_url").text
    assert back == "See https://facebook.com/johnlim1998 and facebook.com/johnlim1998.", back


@pytest.mark.parametrize(
    "link,shape",
    [
        ("https://www.facebook.com/tan.meiling.88", r"https://www\.facebook\.com/user\d+"),
        ("www.meilingtan.com/about/family", r"www\.example\.org/user\d+/page\d+"),
        ("instagram.com/meiling_tan88", r"instagram\.com/user\d+"),
        (
            "http://blog.example.net/posts/2026/meiling?ref=fb",
            r"http://example\.org(/\w+){3}\?id=\d+",
        ),
    ],
)
def test_three_link_forms_are_substituted(tmp_path, link, shape):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"), load_pack("disability"), use_presidio=False, use_gliner=False
    )
    res = s.sanitise(f"Her profile is at {link}. She posts daily.", "u", seed=4)
    new = next(n for h, n, k in res.replacements if h.category == "URL")
    assert link not in res.text and re.fullmatch(shape, new), (res.text, new)
    assert res.text == f"Her profile is at {new}. She posts daily.", res.text


def test_a_pack_can_withhold_links(tmp_path):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("domestic-violence"),
        use_presidio=False,
        use_gliner=False,
    )
    res = s.sanitise("She shares updates at https://t.me/kavitha_r84 with friends.", "u", seed=4)
    assert res.text == "She shares updates at [link withheld] with friends.", res.text


def test_a_home_page_in_a_reply_is_not_an_invented_identifier(tmp_path):
    from socareguard.inbound.leakcheck import leak_check
    from socareguard.inbound.restore import restore

    vault = Vault(tmp_path / "v.sqlite")
    reply = "More at www.msf.gov.sg, or her page https://example.org/user99 may help."
    res = leak_check(
        reply, restore(reply, vault, "h"), vault, "h", set(), use_presidio=False, use_gliner=False
    )
    assert [x.text for x in res.invented] == ["https://example.org/user99"], res.invented


# YOUTH-N2: the gang name leaked on every mention after the one that introduced it.


def test_a_withheld_gang_name_is_withheld_at_every_mention(monkeypatch, tmp_path):
    from socareguard.inbound.restore import restore

    res, _ = _out(monkeypatch, tmp_path, "youth_gang", audience="external")
    out = res.text
    assert "Eagles" not in out, out
    assert out.count("[affiliation withheld]") == 4, out
    assert "linked to [affiliation withheld] tags" in out, out
    vault = Vault(tmp_path / "v.sqlite")
    # a later turn in the same session names the group without the cue word
    s = Sanitiser(vault, load_pack("youth-offending"), audience="external")
    later = s.sanitise("Red Eagles members waited outside the school on Monday.", "youth_gang")
    assert later.text == "[affiliation withheld] members waited outside the school on Monday."
    # the practitioner's own copy restores the group's name
    back = restore("He wants to leave [affiliation withheld].", vault, "youth_gang").text
    assert back == "He wants to leave the 'Red Eagles'.", back


# YOUTH-N3: "his employer's HR department" became "his Foxglove Services"; the case manager's
# "his warehouse job" and the DPO's "a note for an employer" took invented company names too.


@pytest.mark.parametrize(
    "name,audience,phrase",
    [
        ("youth_employer", "external", "his employer's HR department"),
        ("dcm_ownwords", "internal", "his warehouse job"),
        ("dpo_url", "internal", "a note for an employer"),
    ],
)
def test_a_generic_employer_phrase_stays_generic(monkeypatch, tmp_path, name, audience, phrase):
    res, note = _out(monkeypatch, tmp_path, name, audience=audience)
    assert res.text.count(phrase) == note["text"].count(phrase) > 0, res.text
    assert not re.search(r"\b(?:Services|Company|Enterprise)\b", res.text), res.text


def test_a_named_employer_still_takes_a_surrogate_internally(tmp_path):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("disability"),
        use_presidio=False,
        use_gliner=False,
        audience="internal",
    )
    res = s.sanitise("He works at Tan Brothers Holdings; his employer's HR team says so.", "e")
    assert "Tan Brothers Holdings" not in res.text, res.text
    assert "his employer's HR team says so." in res.text, res.text


# META-N2, META-N4 on the meta-reviewer's note: the negative PPO clause was dropped, and the
# plan's review interval was withheld as a safety plan.


def test_a_ppo_clause_after_a_denial_keeps_its_status(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "wsdm_dv", audience="external")
    assert (
        "Denied physical violence by a family member and no protection order is on record."
        in res.text
    ), res.text


@pytest.mark.parametrize(
    "text,want",
    [
        (
            "She denies any physical violence and there is no PPO",
            "denied physical violence by a family member and no protection order is on record",
        ),
        (
            "She said her husband hit her last week and there is no PPO yet",
            "disclosed physical violence by her husband and no protection order is on record",
        ),
    ],
)
def test_dv_rule_generalises_the_ppo_sub_clause(text, want):
    got = generalise_attribute(
        "dv_disclosure", text, "keep_event_drop_specifics", "domestic-violence"
    )
    assert got.lower() == want, got


def test_a_review_interval_is_not_a_safety_plan(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "wsdm_dv", audience="external")
    assert res.text.endswith(
        "Plan: sleep routine for Guo Wei, speak to school counsellor, review in two weeks."
    ) or res.text.endswith("speak to school counsellor, review in two weeks."), res.text
    assert "[safety plan withheld" not in res.text, res.text


def test_a_safety_plan_with_a_cue_is_still_withheld(tmp_path):
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"),
        load_pack("domestic-violence"),
        use_presidio=False,
        use_gliner=False,
    )
    res = s.sanitise("Safety plan: she keeps a packed bag at her sister's flat.", "sp", seed=2)
    assert "packed bag" not in res.text and "withheld" in res.text, res.text


# UIUX-F1: an age already written as a range was banded again ("15 to 17 to 17").


def test_an_age_range_is_not_banded_again(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "uiux_band")
    assert ", age 15 to 17, Sec 3" in res.text, res.text
    assert "to 17 to" not in res.text, res.text
    # a model's misread "employer" ("community service") does not keep the offence as written
    assert "shop theft" not in res.text and "convicted of a property offence" in res.text


@pytest.mark.parametrize(
    "text,want", [("age 15 to 17", []), ("aged 14-16", []), ("Client, age 15, Sec 3", ["15"])]
)
def test_the_age_detector_skips_a_range(text, want):
    from socareguard.detect.gazetteers import find_ages

    assert [h.text for h in find_ages(text)] == want


# Found on the youth advocate's initials letter: a request that names no offence left as
# "No prior offence record is noted", and the model then wrote that the client had no record.


def test_a_request_that_names_no_offence_is_not_a_record_statement(monkeypatch, tmp_path):
    res, _ = _out(monkeypatch, tmp_path, "youth_initials", audience="external")
    assert res.text.endswith(
        "Requesting the school's support to monitor attendance without disclosing the offence to"
        " classmates."
    ), res.text
    assert "No prior offence record" not in res.text, res.text
