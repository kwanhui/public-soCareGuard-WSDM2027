"""Layer 2: deterministic placeholder substitution with exact gold spans."""

from __future__ import annotations

import random
from datetime import date
from typing import Any

from socareguard.corpus import identifiers as ids
from socareguard.corpus.generate import PLACEHOLDER_RE, git_commit
from socareguard.corpus.names import ORIGINS, PersonName, make_name
from socareguard.corpus.schema import (
    PLACEHOLDER_CATEGORIES,
    CodeSwitch,
    Note,
    Span,
    SpanType,
    Template,
)

FEMALE_ROLES = {
    "mother",
    "sister",
    "wife",
    "aunt",
    "grandmother",
    "daughter",
    "girlfriend",
    "mum",
    "stepmother",
}
MALE_ROLES = {
    "father",
    "brother",
    "husband",
    "uncle",
    "grandfather",
    "son",
    "boyfriend",
    "dad",
    "stepfather",
    "ex-husband",
}
FAMILY_ROLES = (
    FEMALE_ROLES
    | MALE_ROLES
    | {"cousin", "sibling", "relative", "grandparent", "partner", "ex-partner"}
)


class _Entities:
    """Per-note entity registry so that every mention of an entity is consistent."""

    def __init__(self, template: Template, rng: random.Random):
        self.rng = rng
        b = template.brief
        self.pack = b.pack
        self.age = b.client_age
        self.note_date = date.fromisoformat(b.note_date)
        self.client = make_name(
            rng,
            b.client_origin,
            b.client_gender,
            b.client_age,
            married_hint=(b.pack == "domestic-violence"),
        )
        self.third: dict[str, PersonName] = {}
        self.address: ids.Address | None = None
        self._cache: dict[str, str] = {}

    def person(self, role: str) -> PersonName:
        role = role.strip().lower()
        if role not in self.third:
            if role in FEMALE_ROLES:
                gender = "female"
            elif role in MALE_ROLES:
                gender = "male"
            else:
                gender = self.rng.choice(["female", "male"])
            origin = self.client.origin if role in FAMILY_ROLES else self.rng.choice(ORIGINS)
            age = 40 if role in FAMILY_ROLES else 35
            if role in {"son", "daughter", "friend", "sibling", "cousin"}:
                age = max(8, self.age + self.rng.randint(-3, 3))
            self.third[role] = make_name(
                self.rng, origin, gender, age, married_hint=role in {"mother", "wife"}
            )
        return self.third[role]

    def value(self, key: str, arg: str | None) -> tuple[str, str, str | None]:
        """Return (surface text, entity_id, origin) for a placeholder."""
        if key.startswith("CLIENT_"):
            return self.client.form(key), "client", self.client.origin
        if key.startswith("TP_"):
            role = arg or "third party"
            p = self.person(role)
            return p.form(key), f"tp:{role.strip().lower()}", p.origin
        if key == "ATTR":
            k, _, text = (arg or "").partition("=")
            return text, f"attr:{k}", None
        cache_key = f"{key}:{arg}" if arg else key
        if cache_key in self._cache:
            return self._cache[cache_key], cache_key.lower(), None
        birth_year = self.note_date.year - self.age
        if key == "NRIC":
            v = ids.make_nric(self.rng, birth_year=birth_year)
        elif key == "DOB":
            v = ids.format_dob(self.rng, ids.make_dob(self.rng, self.age, self.note_date))
        elif key == "AGE":
            v = str(self.age)
        elif key in {"ADDRESS", "ESTATE"}:
            if self.address is None:
                self.address = ids.make_address(self.rng)
            v = str(self.address) if key == "ADDRESS" else self.address.estate
        elif key == "PHONE":
            v = ids.make_phone(self.rng)
        elif key == "CASE_REF":
            v = ids.make_case_ref(self.rng, self.pack, self.note_date.year)
        elif key == "SCHOOL":
            v = ids.make_school(self.rng, self.age)
        elif key == "EMPLOYER":
            v = ids.make_employer(self.rng)
        elif key == "FACILITY":
            v = ids.make_facility(self.rng, (arg or "family service centre").strip().lower())
        else:
            raise KeyError(key)
        self._cache[cache_key] = v
        return v, cache_key.lower(), None


def _at_sentence_start(prefix: str) -> bool:
    stripped = prefix.rstrip(" ")
    return stripped == "" or stripped.endswith((".", "!", "?", "\n", ":"))


def inject(template: Template, seed_offset: int = 7) -> Note:
    rng = random.Random(template.seed + seed_offset)
    ents = _Entities(template, rng)
    out: list[str] = []
    spans: list[Span] = []
    switches: list[CodeSwitch] = []
    pos = 0
    cursor = 0
    for m in PLACEHOLDER_RE.finditer(template.template_text):
        out.append(template.template_text[cursor : m.start()])
        pos += m.start() - cursor
        key, arg = m.group(1), m.group(2)
        if key == "CS":
            lang, _, text = (arg or "").partition("=")
            out.append(text)
            switches.append(CodeSwitch(start=pos, end=pos + len(text), lang=lang, text=text))
            pos += len(text)
        else:
            text, entity_id, origin = ents.value(key, arg)
            if key == "ATTR" and text and _at_sentence_start("".join(out)):
                text = text[0].upper() + text[1:]
            stype, category = PLACEHOLDER_CATEGORIES[key]
            spans.append(
                Span(
                    start=pos,
                    end=pos + len(text),
                    text=text,
                    type=stype,
                    category=category,
                    placeholder=key,
                    arg=(arg.partition("=")[0] if key == "ATTR" else arg),
                    entity_id=entity_id,
                    origin=origin,
                )
            )
            out.append(text)
            pos += len(text)
        cursor = m.end()
    out.append(template.template_text[cursor:])
    text = "".join(out)
    return Note(
        id=template.id,
        pack=template.pack,
        seed=template.seed,
        brief=template.brief,
        template_text=template.template_text,
        text=text,
        spans=spans,
        code_switches=switches,
        generation=template.generation,
        injection_commit=git_commit(),
    )


def span_stats(notes: list[Note]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_cat: dict[str, int] = {}
    by_origin: dict[str, int] = {}
    by_attr: dict[str, int] = {}
    cs: dict[str, int] = {}
    for n in notes:
        for s in n.spans:
            by_type[s.type.value] = by_type.get(s.type.value, 0) + 1
            by_cat[s.category] = by_cat.get(s.category, 0) + 1
            if s.origin and s.category in {"NAME", "THIRD_PARTY_NAME"}:
                by_origin[s.origin] = by_origin.get(s.origin, 0) + 1
            if s.type is SpanType.ATTRIBUTE and s.arg:
                by_attr[s.arg] = by_attr.get(s.arg, 0) + 1
        for c in n.code_switches:
            cs[c.lang] = cs.get(c.lang, 0) + 1
    return {
        "notes": len(notes),
        "spans": sum(len(n.spans) for n in notes),
        "by_type": dict(sorted(by_type.items())),
        "by_category": dict(sorted(by_cat.items())),
        "name_spans_by_origin": dict(sorted(by_origin.items())),
        "attribute_spans_by_key": dict(sorted(by_attr.items())),
        "notes_with_code_switch": sum(1 for n in notes if n.code_switches),
        "code_switch_fragments_by_lang": dict(sorted(cs.items())),
        "client_origin_by_note": dict(
            sorted(
                {o: sum(1 for n in notes if n.brief.client_origin == o) for o in ORIGINS}.items()
            )
        ),
    }
