"""Deterministic Singapore identifier recognisers.

Each recogniser returns character spans with a category matching the corpus gold
categories, so detector output can be scored directly against ``Note.spans``.
NRIC/FIN matches are checksum-validated; a pattern match with a wrong check letter is
reported at a lower score rather than dropped, because practitioners mistype.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from socareguard.corpus.identifiers import SECTORS, is_valid_nric


@dataclass(frozen=True)
class Hit:
    start: int
    end: int
    text: str
    category: str
    detector: str
    score: float


NRIC_RE = re.compile(r"\b[STFGMstfgm]\d{7}[A-Za-z]\b")
POSTAL_RE = re.compile(r"(?<![\d-])(?:Singapore\s+|S\(?)?(\d{6})\)?(?![\d-])")
UNIT_RE = re.compile(r"#\s?\d{1,2}-\d{1,4}\b")
BLOCK_RE = re.compile(r"\b(?:Blk|Block)\s+\d{1,4}[A-Z]?\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+65[\s-]?)?[3689]\d{3}[\s-]?\d{4}(?!\d)")
CASE_REF_RE = re.compile(r"\b(?:YC|JRC|PROB|FSC|PPO|FVSC|DSC|SSA|CM)[/-]\d{2,4}[/-]\d{3,4}\b")
DOB_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-](?:19|20)\d{2}|(?:19|20)\d{2}-\d{2}-\d{2}|"
    r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(?:19|20)\d{2})\b"
)
_VALID_SECTORS = {s for secs in SECTORS.values() for s in secs}


def find_nric(text: str) -> list[Hit]:
    out = []
    for m in NRIC_RE.finditer(text):
        v = m.group(0)
        score = 1.0 if is_valid_nric(v) else 0.6
        out.append(Hit(m.start(), m.end(), v, "NRIC", "sg.nric", score))
    return out


def find_postal(text: str) -> list[Hit]:
    out = []
    for m in POSTAL_RE.finditer(text):
        digits = m.group(1)
        # Six digits alone are weak evidence; a known HDB sector or a 'Singapore' prefix raises it.
        score = 0.5
        if m.group(0).lower().startswith(("singapore", "s(")):
            score = 0.95
        elif digits[:2] in _VALID_SECTORS:
            score = 0.7
        out.append(Hit(m.start(), m.end(), m.group(0), "ADDRESS", "sg.postal", score))
    return out


def find_unit(text: str) -> list[Hit]:
    return [
        Hit(m.start(), m.end(), m.group(0), "ADDRESS", "sg.unit", 0.9)
        for m in UNIT_RE.finditer(text)
    ]


def find_block(text: str) -> list[Hit]:
    return [
        Hit(m.start(), m.end(), m.group(0), "ADDRESS", "sg.block", 0.8)
        for m in BLOCK_RE.finditer(text)
    ]


def find_phone(text: str) -> list[Hit]:
    out = []
    for m in PHONE_RE.finditer(text):
        v = m.group(0)
        digits = re.sub(r"\D", "", v)[-8:]
        score = 0.9 if digits[0] in "89" else 0.7
        out.append(Hit(m.start(), m.end(), v, "PHONE", "sg.phone", score))
    return out


def find_case_ref(text: str) -> list[Hit]:
    return [
        Hit(m.start(), m.end(), m.group(0), "CASE_REF", "sg.caseref", 0.9)
        for m in CASE_REF_RE.finditer(text)
    ]


def find_dob(text: str) -> list[Hit]:
    """Date patterns. Only a date near a birth cue is a DOB; others are dates of contact."""
    out = []
    for m in DOB_RE.finditer(text):
        window = text[max(0, m.start() - 25) : m.start()].lower()
        is_dob = any(cue in window for cue in ("dob", "d.o.b", "born", "birth"))
        out.append(
            Hit(
                m.start(),
                m.end(),
                m.group(0),
                "DOB" if is_dob else "DATE",
                "sg.date",
                0.9 if is_dob else 0.3,
            )
        )
    return out


def find_all(text: str) -> list[Hit]:
    hits = (
        find_nric(text)
        + find_postal(text)
        + find_unit(text)
        + find_block(text)
        + find_phone(text)
        + find_case_ref(text)
        + find_dob(text)
    )
    return _dedupe(sorted(hits, key=lambda h: (h.start, -h.end)))


def _dedupe(hits: list[Hit]) -> list[Hit]:
    """Drop a hit fully inside an earlier, higher-scoring hit (e.g. postal inside address)."""
    kept: list[Hit] = []
    for h in hits:
        if any(k.start <= h.start and h.end <= k.end and k.score >= h.score for k in kept):
            continue
        kept.append(h)
    return kept
