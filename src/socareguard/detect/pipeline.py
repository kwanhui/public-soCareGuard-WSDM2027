"""Chained detection: SG recognisers + gazetteers + Presidio + GLiNER, merged into one span list.

Merge policy: overlapping hits are resolved by (1) a DIRECT category beats a QUASI one,
(2) higher score, (3) longer span. AGE hits are kept only when they do not sit inside
another span. Attribute hits (``ATTR:<key>``) are returned separately: they are
generalisation targets and may legitimately overlap entity spans.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from socareguard.corpus import names as nm
from socareguard.detect import backends, gazetteers, sg
from socareguard.detect.attributes import find_attributes
from socareguard.detect.sg import Hit

DIRECT = {
    "NAME",
    "NRIC",
    "PHONE",
    "ADDRESS",
    "DOB",
    "CASE_REF",
    "EMAIL",
    "PASSPORT",
    "BANK_ACCOUNT",
    "HANDLE",
    "MRN",
    "WARD_BED",
    "VEHICLE",
}
QUASI = {"SCHOOL", "ESTATE", "AGE", "EMPLOYER", "FACILITY"}
PRIORITY = {c: 2 for c in DIRECT} | {c: 1 for c in QUASI} | {"DATE": 0}


@dataclass
class Detection:
    entities: list[Hit] = field(default_factory=list)
    attributes: list[Hit] = field(default_factory=list)
    detectors: list[str] = field(default_factory=list)


# Role words and case-note abbreviations that name a relationship, never a person.
ROLE_WORDS = {
    "clt", "client", "pt", "patient", "dtr", "daughter", "son", "hubby", "husband", "wife",
    "nok", "sis", "bro", "mum", "mom", "dad", "gran", "grandma", "grandpa", "granny", "auntie",
    "uncle", "intern", "sw", "worker", "officer", "teacher", "supervisor", "principal", "admin",
    "cw", "fsw", "msw", "po", "pp", "ic", "kin", "spouse", "partner", "mother", "father",
    "self", "ward", "bed", "room", "mrn", "nurse", "doctor", "dr", "staff", "ot", "physio",
    "attends", "lives", "works", "stays", "reports", "states", "says", "said", "denies", "presented",
    "seen", "noted", "plan", "assessment", "observations", "contact", "referred", "declined",
    "agreed", "attended", "called", "visited", "discussed", "advised", "informed", "confirmed",
}  # fmt: skip
AGENCY_STOPLIST = {
    "hdb",
    "ppo",
    "deo",
    "cpo",
    "fjc",
    "cypa",
    "mca",
    "pdpa",
    "comcare smta",
    "comcare lta",
    "comcare",
    "smta",
    "lta",
    "moe fas",
    "fas",
    "medifund",
    "medisave",
    "medishield",
    "chas",
    "comlink",
    "cpf",
    "kkh",
    "sgh",
    "nuh",
    "ttsh",
    "cgh",
    "ktph",
    "ntfgh",
    "cdc",
    "pa",
    "sg enable",
    "agency for integrated care",
    "fsc",
    "sso",
    "msf",
    "moe",
    "dac",
    "imh",
    "spf",
    "ncss",
    "aic",
    "mendaki",
    "sinda",
    "cdac",
    "youth court",
    "family justice courts",
    "police",
    "polyclinic",
    "gp",
    "ite",
    "mrt",
    "town council",
    "hdb flat",
    "family service centre",
    "social service office",
    "day activity centre",
    "singapore",
    "mom",
    "wsg",
    "e2i",
}
_LEADING_STOP = {
    "attends",
    "attend",
    "client",
    "visited",
    "lives",
    "referred",
    "at",
    "the",
    "from",
    "to",
    "in",
    "contact",
    "met",
    "seen",
}
_LINK_WORDS = {
    "bin",
    "binti",
    "binte",
    "bte",
    "bt",
    "s/o",
    "d/o",
    "a/l",
    "a/p",
    "mdm",
    "mr",
    "ms",
    "mrs",
    "master",
    "encik",
    "cik",
    "puan",
}
_SURNAMES = {x.lower() for x in nm._CHINESE_SURNAMES + nm._EURASIAN_SURNAMES + nm._WESTERN_SURNAMES}
_TITLE_PREFIX = re.compile(r"^(?:Mdm|Mr|Mrs|Ms|Master|Encik|Cik|Puan|Dr)\.?\s", re.IGNORECASE)


_PATRONYMIC = re.compile(
    r"^\s(?:bin|binti|binte|bte|bt|s/o|d/o|a/l|a/p)\s[A-Z][a-z]+(?:\s[A-Z][a-z]+)?"
)


_ADDRESS_NEXT = {
    "road", "rd", "street", "st", "avenue", "ave", "drive", "dr", "lane", "crescent", "cres",
    "close", "walk", "way", "link", "loop", "rise", "view", "central", "north", "south", "east",
    "west", "ring", "hill", "grove", "park", "terrace", "place", "heights", "gardens", "garden",
    "lorong", "lor", "jalan", "jln", "taman", "kampong", "upper", "lower", "mount", "bukit",
    "industrial", "estate", "town", "new", "old", "vale", "green", "field", "square", "boulevard",
    "sector", "circle", "mall", "point", "plaza",
}  # fmt: skip


def _estate_in_org_name(text: str, hits: list[Hit]) -> list[Hit]:
    """'Changi' in 'Changi Airport Terminal 3' or 'Bedok' in 'Bedok Youth Centre' names an
    organisation, not the client's estate: extend over the capitalised words and treat it as a
    facility so it is generalised as a service provider, never as a region."""
    out = []
    for h in hits:
        if h.category == "ESTATE":
            m = re.match(r"(?:\s+[A-Z][A-Za-z'’]+|\s+\d+[A-Z]?)+", text[h.end : h.end + 60])
            if m:
                nxt = m.group(0).split()[0].lower()
                if nxt not in _ADDRESS_NEXT and not re.match(r"\d", nxt):
                    end = h.end + m.end()
                    out.append(
                        Hit(h.start, end, text[h.start : end], "FACILITY", "gazetteer.org", 0.9)
                    )
                    continue
        out.append(h)
    return out


def _extend_names(text: str, hits: list[Hit]) -> list[Hit]:
    """A NAME hit preceded by a known surname token ('Teo' before 'Shu Fen') is extended to include
    it, and a hit followed by a patronymic ('Priya' before 'd/o Muthusamy') is extended over it."""
    out = []
    for h in hits:
        if h.category == "NAME":
            m = re.search(r"([A-Z][a-z]+)\s$", text[: h.start])
            if m and m.group(1).lower() in _SURNAMES:
                h = Hit(m.start(1), h.end, text[m.start(1) : h.end], "NAME", h.detector, h.score)
            m2 = _PATRONYMIC.match(text[h.end : h.end + 60])
            if m2:
                end = h.end + m2.end()
                h = Hit(h.start, end, text[h.start : end], "NAME", h.detector, h.score)
        out.append(h)
    return out


_CURRENT_YEAR = __import__("datetime").date.today().year
_TRUST = {"sg": 3, "gazetteer": 3, "propagate": 2, "gliner": 1, "presidio": 0}


def _trust(h: Hit) -> int:
    return _TRUST.get(h.detector.split(".")[0], 1)


def _sane(h: Hit) -> bool:
    t = h.text.strip()
    core = re.sub(r"[^\w/ ]", "", t).lower()
    if h.category in {"EMPLOYER", "FACILITY", "ESTATE", "NAME"} and (
        core in AGENCY_STOPLIST
        or core.replace(" ", "") in {a.replace(" ", "") for a in AGENCY_STOPLIST}
    ):
        return False
    if h.category in {"EMPLOYER", "FACILITY", "ESTATE"} and _TITLE_PREFIX.match(t):
        return False
    if h.category == "DOB":
        yr = re.search(r"(19|20)\d{2}", t)
        if yr and int(yr.group(0)) >= _CURRENT_YEAR - 1:
            return False
    if h.category == "DOB" and not re.search(
        r"(19|20)\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2}\b", t, re.IGNORECASE
    ):
        # A date of birth carries a year. "2 Sep" is a date of contact, never a DOB.
        return False
    if h.category == "ADDRESS" and not re.search(r"\d", t):
        return False
    if h.category == "PHONE" and len(re.sub(r"\D", "", t)) < 7:
        return False
    if h.category == "NRIC" and not re.fullmatch(r"[STFGMstfgm]\d{7}[A-Za-z]", t):
        return False
    if h.category == "NAME" and _TITLE_PREFIX.sub("", t).strip().lower() in ROLE_WORDS:
        return False
    if h.category == "NAME" and any(
        w in ROLE_WORDS for w in re.split(r"\s+", _TITLE_PREFIX.sub("", t).lower())[:1]
    ):
        return False  # "Ward 9B", "Son says": the first token names a role or a place, not a person
    if h.category in {"FACILITY", "SCHOOL", "EMPLOYER"} and not any(c.isupper() for c in t):
        return False  # "the void deck", "a coffee shop": a place, not a named facility
    if h.category == "NAME" and not any(c.isupper() for c in t):
        return False
    return not (
        h.category == "NAME"
        and (not re.search(r"[A-Za-z]", t) or len(t) < 2 or t.lower() in _LINK_WORDS)
    )


def _propagate_names(text: str, hits: list[Hit]) -> list[Hit]:
    """Every capitalised token of a detected name is a name elsewhere in the same text."""
    tokens: set[str] = set()
    for h in hits:
        if h.category != "NAME":
            continue
        for tok in re.split(r"[\s,()]+", h.text):
            if (
                len(tok) >= 3
                and tok[0].isupper()
                and tok.lower() not in _LINK_WORDS
                and tok.lower() not in ROLE_WORDS
                and tok.isalpha()
            ):
                tokens.add(tok)
    out = []
    for tok in tokens:
        for m in re.finditer(r"(?<![\w])" + re.escape(tok) + r"(?![\w])", text):
            if not any(k.start <= m.start() and m.end() <= k.end for k in hits):
                out.append(Hit(m.start(), m.end(), tok, "NAME", "propagate", 0.75))
    return out


def _merge_addresses(text: str, hits: list[Hit]) -> list[Hit]:
    """Join block / street / unit / postal parts into one ADDRESS span. An ESTATE hit is absorbed
    only when another address part follows it (a street name), never as a trailing town."""
    out: list[Hit] = []
    i = 0
    while i < len(hits):
        h = hits[i]
        if h.category != "ADDRESS":
            out.append(h)
            i += 1
            continue
        start, end, score, j = h.start, h.end, h.score, i + 1
        while j < len(hits) and hits[j].category in {"ADDRESS", "ESTATE"}:
            gap = text[end : hits[j].start]
            if len(gap) > 40 or "\n" in gap or "." in gap:
                break
            if hits[j].category == "ESTATE":
                nxt = hits[j + 1] if j + 1 < len(hits) else None
                if not (
                    nxt and nxt.category == "ADDRESS" and len(text[hits[j].end : nxt.start]) <= 40
                ):
                    break
            end, score = hits[j].end, max(score, hits[j].score)
            j += 1
        out.append(
            Hit(
                start,
                end,
                text[start:end],
                "ADDRESS",
                "sg.address" if j > i + 1 else h.detector,
                score,
            )
        )
        i = j
    return out


def _trim_leading(h: Hit) -> Hit:
    """'Attends Sunbeam Day Activity Centre' -> 'Sunbeam Day Activity Centre'."""
    if h.category not in {"FACILITY", "SCHOOL"}:
        return h
    first, _, rest = h.text.partition(" ")
    if first.lower() in _LEADING_STOP and rest:
        return Hit(h.start + len(first) + 1, h.end, rest, h.category, h.detector, h.score)
    return h


def _resolve(hits: list[Hit]) -> list[Hit]:
    hits = [_trim_leading(h) for h in hits if h.category != "DATE" and _sane(h)]
    ranked = sorted(
        hits,
        key=lambda h: (
            -_trust(h),
            -PRIORITY.get(h.category, 0),
            -h.score,
            -(h.end - h.start),
            h.start,
        ),
    )
    kept: list[Hit] = []
    for h in ranked:
        if any(k.start < h.end and h.start < k.end for k in kept):
            continue
        kept.append(h)
    return sorted(kept, key=lambda h: h.start)


def _merge_attributes(hits: list[Hit]) -> list[Hit]:
    """Overlapping attribute hits of the same key collapse to the longest; different keys may overlap."""
    kept: list[Hit] = []
    for h in sorted(hits, key=lambda h: (-(h.end - h.start), h.start)):
        if any(k.category == h.category and k.start < h.end and h.start < k.end for k in kept):
            continue
        kept.append(h)
    return sorted(kept, key=lambda h: h.start)


def detect(
    text: str,
    use_presidio: bool = True,
    use_gliner: bool = True,
    attributes: bool = True,
    min_score: float = 0.5,
    attribute_keys: set[str] | None = None,
) -> Detection:
    hits = sg.find_all(text) + gazetteers.find_all(text)
    used = ["sg", "gazetteer"]
    if use_presidio:
        hits += backends.presidio_hits(text)
        used.append("presidio")
    attrs: list[Hit] = []
    if attributes:
        attrs = find_attributes(text, keys=attribute_keys)
    if use_gliner:
        hits += backends.gliner_hits(text)
        used.append(backends.gliner_backend_name())
        if attributes:
            attrs = _merge_attributes(attrs + backends.gliner_attribute_hits(text))
    ents = _resolve(_estate_in_org_name(text, [h for h in hits if h.score >= min_score]))
    ents = _resolve(_extend_names(text, ents))
    ents = _resolve(ents + _propagate_names(text, ents))
    ents = _merge_addresses(text, ents)
    return Detection(entities=ents, attributes=sorted(attrs, key=lambda h: h.start), detectors=used)
