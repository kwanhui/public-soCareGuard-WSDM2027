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
    (re.compile(r"\bvap\w*|e-cig\w*|tobacco|smok", re.IGNORECASE), "a tobacco or vaping matter"),
    (
        re.compile(r"drug|cannabis|substance|inhalant|meth\b|controlled", re.IGNORECASE),
        "a drug-related offence",
    ),
    (
        re.compile(r"riot|assault|fight|hurt|violen|weapon|robbery", re.IGNORECASE),
        "an offence involving violence",
    ),
    (re.compile(r"truan|absent", re.IGNORECASE), "a school attendance matter"),
    (re.compile(r"cheat|scam|fraud|forg", re.IGNORECASE), "a dishonesty offence"),
]


def _soften(text: str, table: list[tuple[re.Pattern[str], str]]) -> str:
    """Replace only the whole words that name the offence or condition, keeping the sentence."""
    out = text
    for pat, lab in table:
        out = re.sub(r"\b\w*(?:" + pat.pattern + r")\w*\b", lab, out, flags=re.IGNORECASE)
    return out


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
        label = next((lab for pat, lab in table if pat.search(t)), None)
        if key != "offence":
            if len(t.split()) > 12:
                # A long clause keeps its sense; only the words naming the condition are replaced.
                return _soften(t, table) if label else t
            return f"has {label}" if label else "has a health condition"
        # A prior warning stays a prior warning; only a current matter is described as current;
        # a denial, a withdrawn charge or a relative's record is never turned into the client's;
        # a negation stays a negation; an order or a recommendation keeps its terms.
        tl = t.lower()
        what = label or "an offence matter"
        if re.search(
            r"\b(?:no|never|without|not|nil)\b[^.;\n]{0,24}\b(?:previous|prior|record|charge|conviction|offen[cs]\w*|offending|involvement|antecedent|trouble with the law|in trouble|police involvement|history)",
            tl,
        ) or re.search(
            r"\bnever been in trouble\b|\bclean record\b|\bfirst (?:contact|offence|time)\b", tl
        ):
            return "no prior offence record is noted"
        if re.search(
            r"\b(?:denie[sd]|deny|did not know|didn't know|not aware|unaware|no involvement|not involved|maintains? (?:his|her|their) innocence)\b",
            tl,
        ):
            return f"an allegation of {what} is on record; the client disputes it"
        if re.search(
            r"\b(?:withdrawn|dismissed|acquitted|no further action|nfa|discontinued|closed|dropped|not proceeded)\b",
            tl,
        ):
            return f"a matter of {what} is on record and closed"
        if re.search(
            r"\b(?:cousin|brother|sister|father|mother|uncle|aunt|friend|boyfriend|girlfriend|partner|husband|wife|relative|sibling)\b"
            r"[^.;\n]{0,25}\b(?:has|had|was|were|with|holds|got|served|is|been)\b[^.;\n]{0,20}\b(?:convict\w*|criminal record|record|charg\w*|arrest\w*|prison|jail|probation|sentenced)\b",
            tl,
        ):
            return f"a family member or associate has a record of {what}"
        if len(t.split()) > 8 or re.search(
            r"\b(?:order|months?|curfew|cso|community service|hours|recommend\w*|condition\w*|review|outcome|diversion|guidance programme)\b",
            tl,
        ):
            # Keep the sentence; replace only the words that name the offence.
            return _soften(t, OFFENCE_CATEGORIES)
        # "prior" counts as history only next to a record noun: "low prior risk" is not a record.
        past = re.search(
            r"\b(?:prev\w*|prior|past|earlier|previously)\b[^.;\n]{0,12}\b(?:record|conviction|offen[cs]\w*|charge|warning|caution|antecedent|matter|history)\b"
            r"|\b(?:history of|warning|caution)\b",
            tl,
        )
        if re.search(r"\bwarning|caution\b", tl):
            return f"has a prior police warning on record ({what})"
        if past:
            return f"has a prior record of {what}"
        return f"is the subject of a current matter: {what}"
    if rule == "status_only":
        if key == "ppo":
            tl = t.lower()
            past = re.search(
                r"\b(?:20[0-2]\d|last year|previous\w*|earlier|prior|in the past)\b", tl
            )
            if re.search(
                r"\bno\b[^.;\n]{0,25}\b(?:order|ppo|application)\b[^.;\n]{0,30}\b(?:applied|made|sought|in place|granted|filed)|\bnever applied\b|\bno (?:ppo|order) (?:is |has been )?(?:in place|applied)",
                tl,
            ):
                return "no protection order application is on record"
            if len(t.split()) > 12 and not re.search(
                r"^\s*(?:a |the )?(?:ppo|protection order)", tl
            ):
                # An assessment or plan that mentions the order keeps its sense; only the order's
                # specifics are generalised in place.
                return re.sub(
                    r"\b(?:PPO|personal protection order|expedited order|domestic exclusion order|DEO)\b(?:\s+(?:application|hearing))?(?:[^.;\n]{0,25}\b(?:on|dated|until|from)\s+\d{1,2}\s+\w+(?:\s+\d{4})?)?",
                    "the protection order matter",
                    t,
                    flags=re.IGNORECASE,
                )
            if re.search(r"withdraw|declin|does not want|did not want|not to apply|refus", tl):
                if past:
                    return "an earlier protection order application was withdrawn or declined"
                return "the client has decided against a protection order for now"
            if re.search(r"expedited order|\bdeo\b|domestic exclusion", tl) and re.search(
                r"in force|granted|in place|valid|until|expires", tl
            ):
                return "an expedited or exclusion order is in force (expiry on record)"
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
            # A deputy or donee is only evidence against capacity when one is actually in place.
            # "Mother is not her deputy" and "no deputyship order" say the opposite.
            no_proxy = re.search(
                r"\b(?:not|no|isn't|is not|without|nil)\b[^.]{0,20}\b(?:deputy|deputyship|donee|lpa)"
                r"|\b(?:deputy|deputyship|donee|lpa)\b[^.;\n]{0,12}\b(?:none|nil|not appointed|no)\b",
                tl,
            )
            has_proxy = (not no_proxy) and re.search(r"\bdeputy|deputyship|donee|lpa\b", tl)
            negative = (
                re.search(
                    r"lack|unable|not have|no capacity|impair|fluctuat|limited|in question|doubt|unclear",
                    tl,
                )
                or has_proxy
            )
            positive = re.search(
                r"has capacity|have capacity|demonstrat|able to|confirmed|retains capacity|capacity to make|presumed|intact",
                tl,
            )
            if no_proxy and not negative:
                return "no deputy or donee is appointed; capacity is presumed"
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
        # The age is the number next to an age cue, never a day of the month or a year.
        m = re.search(
            r"(?:\b(?:aged?|age:?)\s*(\d{1,2})\b|\b(\d{1,2})\s*(?:-|\s)?(?:year[- ]old|yo|y/o|years?\s+old)\b|,\s*(\d{1,2})\s*,)",
            t,
            re.IGNORECASE,
        )
        age = next((g for g in (m.groups() if m else ()) if g), None)
        return "is a minor aged " + age_band(int(age), 3) if age else "is a minor"
    return t


@dataclass(frozen=True)
class GeneralisationRule:
    rule_id: str
    category: str
    original: str
    generalised: str
