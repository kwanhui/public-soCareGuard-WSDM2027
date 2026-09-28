"""Pattern and gazetteer recognisers for Singapore quasi-identifiers.

Estates, schools, facilities, employers and ages are quasi-identifiers: harmless alone,
re-identifying in combination. Off-the-shelf PII models are entity-typed (NAME, PHONE) and
mostly miss them, so these recognisers cover the gap with Singapore-specific knowledge.
"""

from __future__ import annotations

import re

from socareguard.corpus.identifiers import FACILITIES, SECTORS
from socareguard.detect.sg import Hit
from socareguard.outbound.generalise import MALLS, REGION

ESTATES = sorted(
    set(SECTORS)
    | set(REGION)
    | {
        "Marsiling",
        "Chong Pang",
        "Khatib",
        "Tiong Bahru",
        "Bishan",
        "Bedok North",
        "Tampines North",
        "Jurong",
        "Buangkok",
        "Kovan",
        "Simei",
        "Eunos",
        "Aljunied",
        "Redhill",
        "Telok Blangah",
        "Boon Lay",
        "Pioneer",
        "Yew Tee",
        "Admiralty",
        "Canberra",
        "Kranji",
        "Bukit Gombak",
        "Teck Whye",
        "Holland",
        "Farrer Park",
        "Little India",
        "Paya Lebar",
        "Ubi",
        "MacPherson",
        "Potong Pasir",
        "Braddell",
    },
    key=len,
    reverse=True,
)
_ESTATE_RE = re.compile(r"\b(" + "|".join(re.escape(e) for e in ESTATES) + r")\b")

# A school's name has a proper-noun head. A salutation or a determiner before "School" ("Dear
# School Counsellor", "The School", "Your School") is not a name, so a role that starts with
# "School" after a salutation ("Dear School Principal") is never read as a school.
_NOT_A_NAME_HEAD = (
    r"(?!(?:Dear|The|This|That|These|Those|Your|Our|His|Her|Their|My|Its|A|An|To|Hi|Hello|Attn"
    r"|Attention|Re|From|At|For|Each|Every|Any|Primary|Secondary|Special|Public|Private|Mainstream"
    r"|Local|International|Neighbourhood|New|Current|Previous|Former|Same|Whole|Summer|Sunday"
    r"|Weekend|Night|Boarding|Kindly|Please|Respected|Esteemed|Madam|Sir|Cc|Copy)\b)"
)
SCHOOL_RE = re.compile(
    rf"\b(?:{_NOT_A_NAME_HEAD}[A-Z][A-Za-z'’]+(?:\s+[A-Z][A-Za-z'’]+){{0,3}}\s+(?:Primary|Secondary)\s+School(?:\s+\(Special Education\))?"
    r"|ITE\s+College\s+(?:Central|East|West)|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?\s+Polytechnic"
    rf"|{_NOT_A_NAME_HEAD}[A-Z][A-Za-z'’]+(?:\s+[A-Z][A-Za-z'’]+){{0,3}}\s+(?:Junior College|School))\b"
)

_FACILITY_NAMES = sorted({n for v in FACILITIES.values() for n in v}, key=len, reverse=True)
FACILITY_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(n) for n in _FACILITY_NAMES) + r"|"
    r"[A-Z][A-Za-z'’]+(?:\s+[A-Z][A-Za-z'’]+){0,3}\s+(?:Crisis\s+Shelter|Family\s+Shelter|Shelter|Day\s+Activity\s+Centre|DAC|"
    r"General\s+Hospital|Hospital|Polyclinic|FSC|Family\s+Service\s+Centre|Boys'\s+Home|Girls'\s+Home|Youth\s+Residence|Centre\s+for\s+Youth)"
    r")\b"
)

AGE_RE = re.compile(
    r"(?:\b(?:aged?|age:?)\s*(\d{1,2})\b|\b(\d{1,2})\s*(?:-|\s)?(?:year[- ]old|yo|y/o|years?\s+old|years)\b|(?<=[A-Za-z])\s?\((\d{1,2})(?:\)|\s*,)|\b(\d{1,2})\s?[MF]\b)",
    re.IGNORECASE,
)

EMPLOYER_RE = re.compile(
    r"\b(?:an?\s+)?(?:logistics firm|hawker stall|cleaning contractor|coffee shop|retail outlet|security agency|"
    r"food delivery platform|construction subcontractor|childcare centre|F&B outlet|shipyard|call centre|"
    r"[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+(?:Pte\.?\s+Ltd|Ltd|LLP|Enterprise|Holdings))"
    r"(?:\s+(?:in|at)\s+[A-Z][A-Za-z ]+?(?=[,.;)]|\s+(?:and|where|who|as)\b))?\b"
)


_MALL_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(m) for m in sorted(MALLS, key=len, reverse=True)) + r")(?![\w+])"
    r"|(?-i:\b[A-Z][A-Za-z']+(?:\s+[A-Z][A-Za-z']+){0,2}\s+(?:Mall|Plaza|Shopping Centre))\b",
    re.IGNORECASE,
)


def find_places(text: str) -> list[Hit]:
    """Shopping malls: named places, generalised to their kind, never an employer."""
    out = []
    for m in _MALL_RE.finditer(text):
        # a listed name counts when it is written as a name (capitalised), not as a common word
        if not m.group(0)[:1].isupper():
            continue
        out.append(Hit(m.start(), m.end(), m.group(0), "FACILITY", "gazetteer.place", 0.9))
    return out


def find_estates(text: str) -> list[Hit]:
    return [
        Hit(m.start(), m.end(), m.group(0), "ESTATE", "sg.estate", 0.85)
        for m in _ESTATE_RE.finditer(text)
    ]


def find_schools(text: str) -> list[Hit]:
    return [
        Hit(m.start(), m.end(), m.group(0), "SCHOOL", "sg.school", 0.9)
        for m in SCHOOL_RE.finditer(text)
    ]


def find_facilities(text: str) -> list[Hit]:
    return [
        Hit(m.start(), m.end(), m.group(0), "FACILITY", "sg.facility", 0.85)
        for m in FACILITY_RE.finditer(text)
    ]


def find_ages(text: str) -> list[Hit]:
    out = []
    for m in AGE_RE.finditer(text):
        num = next(g for g in m.groups() if g)
        if not 0 < int(num) < 110:
            continue
        if m.group(3):
            # "(8)" or "(6, school)" is an age only after a capitalised word, a name: "Aqil (8)".
            # After a lower-case word it is a list marker or a count: "appeal (2)".
            before = text[: m.start()].rstrip()
            if not re.search(r"[A-Z][a-z]*$", before):
                continue
        # Report the number only, so the surrounding words are untouched by substitution.
        s = m.start() + m.group(0).index(num)
        if re.match(r"\s*(?:to|-|\u2013)\s*\d{1,3}\b", text[s + len(num) :]) or re.search(
            r"\b\d{1,3}\s*(?:to|-|\u2013)\s*$", text[:s]
        ):
            continue  # already a range ("age 15 to 17"): banding it again reads "15 to 17 to 17"
        out.append(Hit(s, s + len(num), num, "AGE", "sg.age", 0.8))
    return out


def find_employers(text: str) -> list[Hit]:
    return [
        Hit(m.start(), m.end(), m.group(0), "EMPLOYER", "sg.employer", 0.7)
        for m in EMPLOYER_RE.finditer(text)
    ]


def find_all(text: str) -> list[Hit]:
    return (
        find_estates(text)
        + find_places(text)
        + find_schools(text)
        + find_facilities(text)
        + find_ages(text)
        + find_employers(text)
    )
