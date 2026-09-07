from datetime import UTC, datetime

import pytest

from socareguard.corpus.generate import validate_template
from socareguard.corpus.inject import inject
from socareguard.corpus.schema import Brief, GenerationMeta, SpanType, Template

TEMPLATE = (
    "Intake, {{CLIENT_NAME}} (NRIC {{NRIC}}, DOB {{DOB}}), age {{AGE}}, of {{ADDRESS}} in {{ESTATE}}. "
    "Mother {{TP_NAME:mother}} ({{PHONE}}) attended. {{CLIENT_FIRST}} attends {{SCHOOL}}. "
    "{{TP_FIRST:mother}} said {{CS:singlish=he very stubborn one, cannot say him}}. "
    "{{ATTR:minor=He is 14 and under investigation}}; {{ATTR:offence=picked up for shop theft}}. Case {{CASE_REF}}. "
    "Later, {{CLIENT_NAME}} and {{TP_NAME:mother}} agreed to a plan."
)


def make_template(text=TEMPLATE, pack="youth-offending") -> Template:
    brief = Brief(
        pack=pack,
        note_type="intake assessment",
        practitioner_role="probation officer",
        client_gender="male",
        client_age=14,
        client_origin="chinese",
        presenting_concern="shop theft",
        required_placeholders=["CLIENT_NAME", "NRIC", "SCHOOL"],
        attributes=["minor", "offence"],
        code_switch_lang="singlish",
        note_date="2026-08-20",
    )
    meta = GenerationMeta(
        provider="test",
        model="none",
        prompt_hash="0",
        temperature=0.0,
        created_at=datetime.now(UTC),
    )
    return Template(
        id="t-001", pack=pack, seed=123, brief=brief, template_text=text, generation=meta
    )


def test_validate_template_accepts_good_template():
    t = make_template()
    assert validate_template(t.template_text, t.brief, min_words=20) == []


def test_validate_template_flags_problems():
    t = make_template()
    errs = validate_template(
        t.template_text.replace("{{SCHOOL}}", "Yishun Secondary") + " {{BOGUS}}",
        t.brief,
        min_words=20,
    )
    assert any("missing required placeholder SCHOOL" in e for e in errs)
    assert any("unknown placeholder BOGUS" in e for e in errs)


def test_inject_offsets_and_consistency():
    n = inject(make_template())
    assert "{{" not in n.text and "}}" not in n.text
    for s in n.spans:
        assert n.text[s.start : s.end] == s.text
    names = {s.text for s in n.spans if s.placeholder == "CLIENT_NAME"}
    assert len(names) == 1
    mothers = {s.text for s in n.spans if s.placeholder == "TP_NAME"}
    assert len(mothers) == 1
    first = next(s.text for s in n.spans if s.placeholder == "CLIENT_FIRST")
    assert first in next(iter(names))
    by_key = {s.placeholder: s for s in n.spans}
    assert by_key["NRIC"].text[0] == "T"  # born 2012 -> T series
    assert by_key["AGE"].text == "14"
    assert by_key["ESTATE"].text in by_key["ADDRESS"].text
    assert by_key["ADDRESS"].type is SpanType.DIRECT and by_key["SCHOOL"].type is SpanType.QUASI
    attrs = [s for s in n.spans if s.type is SpanType.ATTRIBUTE]
    assert {a.arg for a in attrs} == {"minor", "offence"}
    assert attrs[0].text == "He is 14 and under investigation"
    assert len(n.code_switches) == 1 and n.code_switches[0].lang == "singlish"
    assert (
        n.text[n.code_switches[0].start : n.code_switches[0].end]
        == "he very stubborn one, cannot say him"
    )
    origins = {s.origin for s in n.spans if s.category in {"NAME", "THIRD_PARTY_NAME"}}
    assert origins == {"chinese"}


def test_inject_is_deterministic():
    a, b = inject(make_template()), inject(make_template())
    assert a.text == b.text and a.spans == b.spans


def test_note_rejects_bad_offsets():
    n = inject(make_template())
    data = n.model_dump()
    data["spans"][0]["start"] += 1
    from socareguard.corpus.schema import Note

    with pytest.raises(ValueError):
        Note.model_validate(data)


def test_attr_capitalised_at_sentence_start():
    t = make_template(
        "Intake for {{CLIENT_NAME}}. {{ATTR:minor=he is 14}}; {{ATTR:offence=picked up for theft}}. {{NRIC}} {{SCHOOL}}"
    )
    n = inject(t)
    a = [s for s in n.spans if s.placeholder == "ATTR"]
    assert a[0].text == "He is 14" and n.text[a[0].start : a[0].end] == "He is 14"
    assert a[1].text == "picked up for theft"


def test_validate_rejects_bare_keys_and_empty_text():
    t = make_template()
    errs = validate_template(
        t.template_text + " CASE_REF: filed. {{CS:malay=}}", t.brief, min_words=20
    )
    assert any("plain text" in e and "CASE_REF" in e for e in errs)
    assert any("empty text" in e for e in errs)
    errs = validate_template(t.template_text + " She is a 14-year-old.", t.brief, min_words=20)
    assert any("plain number" in e for e in errs)
