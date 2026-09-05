"""Pattern and gazetteer recognisers for Singapore quasi-identifiers.

Estates, schools, facilities, employers and ages are quasi-identifiers: harmless alone,
re-identifying in combination. Off-the-shelf PII models are entity-typed (NAME, PHONE) and
mostly miss them, so these recognisers cover the gap with Singapore-specific knowledge.
"""

from __future__ import annotations

import re

from socareguard.corpus.identifiers import FACILITIES, SECTORS
from socareguard.detect.sg import Hit
from socareguard.outbound.generalise import REGION

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

SCHOOL_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z'’]+(?:\s+[A-Z][A-Za-z'’]+){0,3}\s+(?:Primary|Secondary)\s+School(?:\s+\(Special Education\))?"
    r"|ITE\s+College\s+(?:Central|East|West)|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?\s+Polytechnic"
    r"|[A-Z][A-Za-z'’]+(?:\s+[A-Z][A-Za-z'’]+){0,3}\s+(?:Junior College|School))\b"
)

_FACILITY_NAMES = sorted({n for v in FACILITIES.values() for n in v}, key=len, reverse=True)
FACILITY_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(n) for n in _FACILITY_NAMES) + r"|"
    r"[A-Z][A-Za-z'’]+(?:\s+[A-Z][A-Za-z'’]+){0,3}\s+(?:Crisis\s+Shelter|Family\s+Shelter|Shelter|Day\s+Activity\s+Centre|DAC|"
    r"General\s+Hospital|Hospital|Polyclinic|FSC|Family\s+Service\s+Centre|Boys'\s+Home|Girls'\s+Home|Youth\s+Residence|Centre\s+for\s+Youth)"
    r")\b"
)

AGE_RE = re.compile(
    r"(?:\b(?:aged?|age:?)\s*(\d{1,2})\b|\b(\d{1,2})\s*(?:-|\s)?(?:year[- ]old|yo|y/o|years?\s+old|years)\b|\((\d{1,2})\)|\b(\d{1,2})\s?[MF]\b)",
    re.IGNORECASE,
)

EMPLOYER_RE = re.compile(
    r"\b(?:an?\s+)?(?:logistics firm|hawker stall|cleaning contractor|coffee shop|retail outlet|security agency|"
    r"food delivery platform|construction subcontractor|childcare centre|F&B outlet|shipyard|call centre|"
    r"[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+(?:Pte\.?\s+Ltd|Ltd|LLP|Enterprise|Holdings))"
    r"(?:\s+(?:in|at)\s+[A-Z][A-Za-z ]+?(?=[,.;)]|\s+(?:and|where|who|as)\b))?\b"
)


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
        # Report the number only, so the surrounding words are untouched by substitution.
        s = m.start() + m.group(0).index(num)
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
        + find_schools(text)
        + find_facilities(text)
        + find_ages(text)
        + find_employers(text)
    )
