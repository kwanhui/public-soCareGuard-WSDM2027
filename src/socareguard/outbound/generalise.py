"""Sensitive-attribute and quasi-identifier generalisation.

This is an operation distinct from entity substitution: the span is replaced by a banded or
categorical form that keeps what the drafting task needs (that a disclosure happened, that a
protection order is pending, an age band, a school level) and drops what re-identifies in a
small jurisdiction. Rules come from the policy pack; the lexicons here are the mapping tables.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REGION: dict[str, str] = {
    "Ang Mo Kio": "the north-east",
    "Bedok": "the east",
    "Bukit Batok": "the west",
    "Bukit Merah": "the central area",
    "Bukit Panjang": "the west",
    "Choa Chu Kang": "the west",
    "Clementi": "the west",
    "Geylang": "the east",
    "Hougang": "the north-east",
    "Jurong East": "the west",
    "Jurong West": "the west",
    "Kallang/Whampoa": "the central area",
    "Kallang": "the central area",
    "Whampoa": "the central area",
    "Pasir Ris": "the east",
    "Punggol": "the north-east",
    "Queenstown": "the central area",
    "Sembawang": "the north",
    "Sengkang": "the north-east",
    "Serangoon": "the north-east",
    "Tampines": "the east",
    "Toa Payoh": "the central area",
    "Woodlands": "the north",
    "Yishun": "the north",
    "Marsiling": "the north",
    "Tuas": "the west",
    "Changi": "the east",
    "Bishan": "the central area",
    "Novena": "the central area",
    "Marine Parade": "the east",
    "Bukit Timah": "the central area",
    "Tanglin": "the central area",
    "Boon Lay": "the west",
}

DISABILITY_CATEGORIES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"intellectual|learning disab|global developmental|down syndrome|autis|asd\b|adhd",
            re.IGNORECASE,
        ),
        "a developmental disability",
    ),
    (
        re.compile(
            r"cerebral palsy|wheelchair|amput|spinal|paraple|quadriple|mobility|muscular|stroke|hemipleg",
            re.IGNORECASE,
        ),
        "a physical disability",
    ),
    (
        re.compile(
            r"schizo|bipolar|depress|anxiety|psychiatric|mental health|psychosis|ocd|ptsd",
            re.IGNORECASE,
        ),
        "a psychiatric condition",
    ),
    (
        re.compile(r"epilep|seizure|brain injury|dementia|parkinson|neurolog", re.IGNORECASE),
        "a neurological condition",
    ),
    (re.compile(r"blind|visual|deaf|hearing|low vision", re.IGNORECASE), "a sensory disability"),
]

OFFENCE_CATEGORIES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"theft|shop ?lift|steal|stole|burglar|vandal|mischief|property", re.IGNORECASE),
        "a property offence",
    ),
    (
        re.compile(r"drug|cannabis|substance|vap|inhalant|meth|controlled", re.IGNORECASE),
        "a drug-related offence",
    ),
    (
        re.compile(r"riot|assault|fight|hurt|violen|weapon|robbery", re.IGNORECASE),
        "an offence involving violence",
    ),
    (re.compile(r"truan|absent", re.IGNORECASE), "a school attendance matter"),
    (re.compile(r"cheat|scam|fraud|forg", re.IGNORECASE), "a dishonesty offence"),
]


def age_band(age: int, width: int) -> str:
    lo = (age // width) * width
    return f"{lo} to {lo + width - 1}"


def generalise_age(text: str, pack_id: str) -> str:
    m = re.search(r"\d{1,3}", text)
    if not m:
        return "an adult" if pack_id != "youth-offending" else "a young person"
    age = int(m.group(0))
    return age_band(age, 3 if age < 21 else 10)


def generalise_estate(text: str) -> str:
    for k, v in REGION.items():
        if k.lower() in text.lower():
            return v
    return "a residential estate"


def generalise_school(text: str) -> str:
    t = text.lower()
    if "primary" in t:
        return "a primary school"
    if "secondary" in t:
        return "a secondary school"
    if "special" in t:
        return "a special education school"
    if "ite" in t or "polytechnic" in t or "junior college" in t or "college" in t:
        return "a post-secondary institution"
    return "a school"


def generalise_facility(text: str) -> str:
    t = text.lower()
    if "shelter" in t or "harapan" in t or "teduh" in t or "haven" in t:
        return "a crisis shelter"
    if "day activity" in t or "dac" in t:
        return "a day activity centre"
    if "hospital" in t or "institute of mental health" in t or "imh" in t:
        return "a hospital"
    if "polyclinic" in t or "clinic" in t:
        return "a clinic"
    if (
        "fsc" in t
        or "family service" in t
        or "care corner" in t
        or "fei yue" in t
        or "montfort" in t
    ):
        return "a family service centre"
    if "home" in t or "youth" in t or "residence" in t or "pertapis" in t:
        return "a youth residential facility"
    return "a service provider"


def generalise_employer(text: str) -> str:
    return "an employer"


def generalise_attribute(
    key: str, text: str, rule: str, pack_id: str, client_gender_hint: str | None = None
) -> str:
    """Apply a pack rule to an attribute span. Returns the outbound text."""
    t = text.strip()
    if rule == "redact":
        return "[safety plan withheld from this draft]" if key == "safety_plan" else "[withheld]"
    if rule == "category":
        table = DISABILITY_CATEGORIES if key in {"disability", "diagnosis"} else OFFENCE_CATEGORIES
        for pat, label in table:
            if pat.search(t):
                return f"has {label}" if key != "offence" else f"is involved in {label}"
        return "has a health condition" if key != "offence" else "is involved in an offence matter"
    if rule == "status_only":
        if key == "ppo":
            tl = t.lower()
            if re.search(
                r"consider|undecided|whether to appl|to apply|want|decid|explor|option|advis|inform|explain",
                tl,
            ):
                return "a protection order is being considered"
            if re.search(
                r"unclear|unsure|uncertain|whether|not known|unknown|to confirm|clarif", tl
            ):
                return "protection order status to be confirmed"
            if re.search(r"expired|lapsed", tl):
                return "a protection order has lapsed"
            if re.search(r"granted|in place|obtained|issued|was made|has a ppo|holds a", tl):
                return "a protection order is in place"
            if re.search(r"withdraw|declin|does not want|did not want|not to apply|refus", tl):
                return "the client has decided against a protection order for now"
            if re.search(r"filed|applied|submitted|pending|hearing|lodged", tl):
                return "a protection order application is pending"
            if re.search(
                r"consider|unsure|undecided|discuss|option|explore|inform|advis|explain|whether", tl
            ):
                return "a protection order is being considered"
            return "protection order status recorded"
        if key == "capacity":
            tl = t.lower()
            negative = re.search(
                r"lack|unable|not have|no capacity|impair|fluctuat|limited|in question|doubt|deputy|donee|unclear",
                tl,
            )
            positive = re.search(
                r"has capacity|have capacity|demonstrat|able to|confirmed|retains capacity|capacity to make",
                tl,
            )
            if negative and not positive:
                return "capacity for this decision is in question"
            if positive and not negative:
                return "has capacity for this decision"
            return "capacity for this decision: see record"
        return f"{key.replace('_', ' ')} recorded"
    if rule == "keep_event_drop_specifics":
        tl = t.lower()
        who = (
            "her husband"
            if "husband" in tl
            else "his wife"
            if "wife" in tl
            else "her partner"
            if "partner" in tl
            else "an adult son"
            if re.search(r"\bson\b", tl)
            else "a family member"
        )
        denied = re.search(
            r"denied|denies|no physical|not been hit|has not been|never hit|without physical|no violence",
            tl,
        )
        physical = re.search(r"hit|push|slap|punch|kick|strangl|hurt|injur|bruis|assault|threw", tl)
        control = re.search(r"monitor|control|isolat|money|phone|threat|financ", tl)
        if denied:
            return f"denied physical violence by {who}" + (
                "; described controlling behaviour" if control else ""
            )
        kind = (
            "physical violence"
            if physical
            else "coercive control"
            if control
            else "family violence"
        )
        return f"disclosed {kind} by {who}"
    if rule == "age_band":
        m = re.search(r"\b(\d{1,2})\b", t)
        return "is a minor aged " + age_band(int(m.group(1)), 3) if m else "is a minor"
    return t


@dataclass(frozen=True)
class GeneralisationRule:
    rule_id: str
    category: str
    original: str
    generalised: str
