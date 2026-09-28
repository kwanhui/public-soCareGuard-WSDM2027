"""Deterministic Singapore identifier recognisers.

Each recogniser returns character spans with a category matching the corpus gold
categories, so detector output can be scored directly against ``Note.spans``.
NRIC/FIN matches are checksum-validated. A pattern match with a wrong check letter is
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


# An NRIC or FIN as practitioners type it: compact, lower case, or with a space or a hyphen between
# the letter and the digits ("S 1234567 D", "S-1234567-D"). The corpus writes the canonical form,
# so the variants are measured on their own stress set (tests/data/nric-variants.jsonl).
NRIC_RE = re.compile(r"\b[STFGMstfgm][ \t-]?\d{7}[ \t-]?[A-Za-z]\b")


def normalise_nric(text: str) -> str:
    """'s 1234567-d' -> 'S1234567D'."""
    return re.sub(r"[\s-]", "", text).upper()


POSTAL_RE = re.compile(r"(?<![\d-])(?:Singapore\s+|S\(?)?(\d{6})\)?(?![\d-])")
UNIT_RE = re.compile(r"#\s?\d{1,2}-\d{1,4}\b")
BLOCK_RE = re.compile(r"\b(?:Blk|Block)\s+\d{1,4}[A-Z]?\b", re.IGNORECASE)
# The street after a block number belongs to the address: "Blk 203 Sengkang East Way", "Blk 834
# Tampines Street 2", "Blk 12 Jalan Bukit Merah". Left out, the estate inside the street name was
# generalised on its own and the rest of the street crossed as written ("Blk 450 the north-east
# East Way").
_STREET_TYPE = (
    r"(?:Road|Rd|Street|St|Avenue|Ave|Drive|Dr|Lane|Crescent|Cres|Close|Walk|Way|Link|Loop|Rise"
    r"|View|Central|North|South|East|West|Terrace|Place|Grove|Hill|Park|Circle|Green|Heights|Vale"
    r"|Ring Road)"
)
STREET_AFTER_BLOCK_RE = re.compile(
    rf"\s+(?:(?:Jalan|Jln|Lorong|Lor)\s+(?:\d{{1,3}}[A-Z]?\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}}"
    rf"(?:\s+\d{{1,3}}[A-Z]?)?"
    rf"|(?:[A-Z][a-z]+\s+){{1,3}}(?:{_STREET_TYPE}|(?:Lorong|Lor)\s+\d{{1,3}}[A-Z]?)"
    rf"(?:\s+\d{{1,3}}[A-Z]?)?)\b"
)
PHONE_RE = re.compile(r"(?<!\d)(?:\+65[\s-]?)?[3689]\d{3}[\s-]?\d{4}(?!\d)")
CASE_REF_RE = re.compile(r"\b(?:YC|JRC|PROB|FSC|PPO|FVSC|DSC|SSA|CM)[/-]\d{2,4}[/-]\d{3,4}\b")
# Passport numbers share the letter-7-digits-letter shape with an NRIC but never its prefixes.
PASSPORT_RE = re.compile(r"\b[A-LN-RU-Z]\d{7}[A-Z]\b")
BANK_ACCOUNT_RE = re.compile(r"(?<![\d-])\d{3}-\d{5,9}-\d{1,3}(?![\d-])")
HANDLE_RE = re.compile(r"(?<![\w@.])@[A-Za-z0-9_.]{3,30}\b")
# A web link: with a scheme, from "www.", or a bare domain followed by a path. A profile or page
# address often carries the person's name ("facebook.com/johnlim1998"), so it is a direct
# identifier whatever the domain.
_URL_CHARS = r"[^\s<>\"'()\[\]{}]"
URL_RE = re.compile(
    rf"(?<![\w@./-])(?:https?://{_URL_CHARS}+|www\.{_URL_CHARS}+"
    r"|(?:[A-Za-z0-9-]+\.)+(?:com|org|net|sg|edu|gov|io|me|co|info|biz|ly|tv|app|page|link|my)"
    rf"(?:\.[a-z]{{2}})?/{_URL_CHARS}*)",
    re.IGNORECASE,
)
# Hospital record numbers and bed locations: the identifiers that matter most in a ward note.
MRN_RE = re.compile(
    r"\b(?:MRN|NRIC/MRN|medical record (?:no|number)|hospital (?:no|number)|case no)\.?[:\s#]*([A-Z]{0,2}\d{6,10})\b",
    re.IGNORECASE,
)
WARD_BED_RE = re.compile(
    r"\b(?:Ward\s+\d{1,3}[A-Z]?(?:\s*,?\s*(?:Bed|Cubicle)\s*\d{1,3})?|(?:Bed|Cubicle)\s*\d{1,3})\b",
    re.IGNORECASE,
)
DOB_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-](?:19|20)\d{2}|(?:19|20)\d{2}-\d{2}-\d{2}|"
    r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(?:19|20)\d{2})\b"
)
# A staff or officer id typed into the note body. The agency formats are a role prefix and a
# number ("SW-1042", "MSW-0457", "PO-2231"), or any id after "staff id", "officer id",
# "employee no." and the like. Case references (FSC-2026-0288, CM-26-0331) have two number
# groups and are not matched.
STAFF_ID_RE = re.compile(
    r"(?<![\w/-])(?:SW|MSW|FSW|SSW|CW|PO|OFF|STF|EMP)-\d{3,6}(?![\w/-])"
    r"|(?i:\b(?:staff|officer|employee|worker|practitioner|student)\s*(?:id|no\.?|number|#)"
    r"\s*[:#]?\s*)(?P<id>[A-Z]{0,4}-?\d{3,8})(?![\w/-])"
)
_VALID_SECTORS = {s for secs in SECTORS.values() for s in secs}


def find_nric(text: str) -> list[Hit]:
    out = []
    for m in NRIC_RE.finditer(text):
        v = m.group(0)
        if _WORK_PERMIT_CUE.search(text[max(0, m.start() - 30) : m.start()]):
            continue  # a work permit number: find_work_permit reports it
        score = 1.0 if is_valid_nric(normalise_nric(v)) else 0.6
        out.append(Hit(m.start(), m.end(), v, "NRIC", "sg.nric", score))
    return out


# A work permit number after its label ("work permit number G1234567N", "WP no. 12345678"). It is
# FIN-shaped or eight digits; it is its own category so that a replacement table never calls it a
# passport.
_WORK_PERMIT_CUE = re.compile(
    r"\b(?:work permit|WP)\s*(?:no\.?|number|#)?\s*[:#]?\s*$", re.IGNORECASE
)
WORK_PERMIT_RE = re.compile(
    r"(?i:\b(?:work permit|WP)\s*(?:no\.?|number|#)?\s*[:#]?\s*)"
    r"(?P<id>[FGMfgm][ -]?\d{7}[ -]?[A-Za-z]|\d{8}|\d[ -]\d{7})\b"
)


def find_work_permit(text: str) -> list[Hit]:
    return [
        Hit(m.start("id"), m.end("id"), m.group("id"), "WORK_PERMIT", "sg.work_permit", 0.95)
        for m in WORK_PERMIT_RE.finditer(text)
    ]


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
    out = []
    for m in BLOCK_RE.finditer(text):
        street = STREET_AFTER_BLOCK_RE.match(text, m.end())
        if street:
            out.append(Hit(m.start(), street.end(), text[m.start() : street.end()], "ADDRESS",
                           "sg.street", 0.85))  # fmt: skip
        else:
            out.append(Hit(m.start(), m.end(), m.group(0), "ADDRESS", "sg.block", 0.8))
    return out


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


def find_staff_id(text: str) -> list[Hit]:
    out = []
    for m in STAFF_ID_RE.finditer(text):
        s, e = m.span("id") if m.group("id") else m.span()
        out.append(Hit(s, e, text[s:e], "STAFF_ID", "sg.staff", 0.9))
    return out


def find_dob(text: str) -> list[Hit]:
    """Date patterns. Only a date near a birth cue is a DOB, and the others are dates of contact."""
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


def find_passport(text: str) -> list[Hit]:
    return [
        Hit(m.start(), m.end(), m.group(0), "PASSPORT", "sg.passport", 0.9)
        for m in PASSPORT_RE.finditer(text)
        if not _WORK_PERMIT_CUE.search(text[max(0, m.start() - 30) : m.start()])
    ]


def find_bank_account(text: str) -> list[Hit]:
    return [
        Hit(m.start(), m.end(), m.group(0), "BANK_ACCOUNT", "sg.bank", 0.85)
        for m in BANK_ACCOUNT_RE.finditer(text)
    ]


def find_urls(text: str) -> list[Hit]:
    out = []
    for m in URL_RE.finditer(text):
        s, e = m.start(), m.end()
        while e > s and text[e - 1] in ".,;:!?":
            e -= 1  # the sentence's own punctuation is not part of the link
        out.append(Hit(s, e, text[s:e], "URL", "sg.url", 0.95))
    return out


def find_handles(text: str) -> list[Hit]:
    return [
        Hit(m.start(), m.end(), m.group(0), "HANDLE", "sg.handle", 0.85)
        for m in HANDLE_RE.finditer(text)
    ]


TITLE_NAME_RE = re.compile(
    r"\b(?:Mdm|Madam|Mr|Mrs|Ms|Miss|Dr|Prof|Professor|Encik|Puan|Cik|Master)\.?\s+(?P<first>[A-Z][a-z]+)"
    # up to three more name tokens ("Mr Jason Lim Wei Kiat"); "Mr Ong Ong Kian Hock" is the
    # titled form followed by the full name, so a repeat of the first token ends the span
    r"(?:\s+(?:bin|binti|binte|bte|s/o|d/o|a/l|a/p)\s+[A-Z][a-z]+|(?:\s+(?!(?P=first)\b)[A-Z][a-z]+){0,3})"
)


def find_title_names(text: str) -> list[Hit]:
    return [
        Hit(m.start(), m.end(), m.group(0), "NAME", "sg.title", 0.9)
        for m in TITLE_NAME_RE.finditer(text)
    ]


PLATE_RE = re.compile(r"\b(?:S|E)[A-Z]{1,2}\s?\d{1,4}\s?[A-Z]\b")


def find_plates(text: str) -> list[Hit]:
    return [
        Hit(m.start(), m.end(), m.group(0), "VEHICLE", "sg.plate", 0.8)
        for m in PLATE_RE.finditer(text)
        if not NRIC_RE.fullmatch(m.group(0)) and not PASSPORT_RE.fullmatch(m.group(0))
    ]


def find_mrn(text: str) -> list[Hit]:
    return [
        Hit(m.start(1), m.end(1), m.group(1), "MRN", "sg.mrn", 0.95) for m in MRN_RE.finditer(text)
    ]


def find_ward_bed(text: str) -> list[Hit]:
    return [
        Hit(m.start(), m.end(), m.group(0), "WARD_BED", "sg.ward", 0.85)
        for m in WARD_BED_RE.finditer(text)
    ]


def find_all(text: str) -> list[Hit]:
    hits = (
        find_nric(text)
        + find_work_permit(text)
        + find_postal(text)
        + find_unit(text)
        + find_block(text)
        + find_phone(text)
        + find_case_ref(text)
        + find_staff_id(text)
        + find_dob(text)
        + find_passport(text)
        + find_bank_account(text)
        + find_handles(text)
        + find_urls(text)
        + find_mrn(text)
        + find_ward_bed(text)
        + find_plates(text)
        + find_title_names(text)
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
