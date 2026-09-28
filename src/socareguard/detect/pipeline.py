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
    "WORK_PERMIT",
    "BANK_ACCOUNT",
    "HANDLE",
    "URL",
    "MRN",
    "WARD_BED",
    "VEHICLE",
    "STAFF_ID",
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
# Kin terms in Malay, Tamil and Singapore Chinese usage ("Mak dia", "his Amma", "Ah Ma"). A NER
# model reads a capitalised kin term as a person; it names a relationship, and the relationship
# must reach the model as written.
KIN_WORDS = {
    "mak", "emak", "ibu", "ayah", "bapa", "abah", "abang", "kakak", "adik", "nenek", "atuk",
    "pakcik", "makcik", "amma", "appa", "paati", "thatha", "mama", "papa",
    "ahma", "ahgong", "ahpa",
}  # fmt: skip
KIN_PHRASES = {"ah ma", "ah mah", "ah gong", "ah kong", "ah pa", "ah mm", "ah mee", "ah boy"}
# Malay pronouns a NER model reads as a name at the start of a quoted sentence ("Saya takut ...").
MALAY_PRONOUNS = {"saya", "aku", "dia", "kami", "kita", "mereka", "awak", "engkau", "kau"}
ROLE_WORDS |= KIN_WORDS | MALAY_PRONOUNS
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
    # courts are public bodies: "appointed by the Family Court" names no one
    "family justice court",
    "family court",
    "family courts",
    "state courts",
    "state court",
    "syariah court",
    "high court",
    "supreme court",
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
    # public bodies are never an employer or a person ("referral to the Housing Development Board")
    "housing development board",
    "housing and development board",
    "housing & development board",
    "hdb branch",
    "cpf board",
    "central provident fund board",
    "ministry of social and family development",
    "ministry of education",
    "ministry of health",
    "ministry of manpower",
    "singapore police force",
    "iras",
    "skillsfuture singapore",
    "workforce singapore",
}
# Common Singapore nouns for shared places and food outlets: never a person and never an employer
# ("Ah Ming's Kopitiam" is a coffee shop named after a person, and the person is the name).
COMMON_NOUNS = {
    "kopitiam", "void deck", "hawker centre", "hawker center", "food centre", "market",
    "wet market", "mall", "shopping mall", "kopi", "kedai", "hdb flat", "hdb", "community club",
    "cc",
}  # fmt: skip
# Kinds of workplace ("a coffee shop in Tampines") are an employer's kind, never a person.
COMMON_WORKPLACES = {"coffee shop", "coffeeshop", "food court", "provision shop", "mama shop"}
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
_TITLE_PREFIX = re.compile(
    r"^(?:Mdm|Mr|Mrs|Ms|Master|Encik|Cik|Puan|Dr|Prof|Professor)\.?\s", re.IGNORECASE
)


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


# Words that begin a Singapore street or place name and never a person's name: "Jalan Membina",
# "Lorong 4", "Bukit Merah". A NAME span that starts with one is a place a NER model misread.
STREET_PREFIX = {
    "jalan", "jln", "lorong", "lor", "bukit", "kampong", "kg", "taman", "tanjong", "lengkok",
    "lengkong", "persiaran", "upper", "lower", "telok", "pasir", "sungei",
}  # fmt: skip


def _street_like(name: str) -> bool:
    toks = _TITLE_PREFIX.sub("", name.strip()).lower().split()
    return bool(toks) and (toks[0] in STREET_PREFIX or any(t in _ADDRESS_NEXT for t in toks[1:]))


def _estates_outside_names(hits: list[Hit]) -> list[Hit]:
    """An estate gazetteer match inside a longer detected person name is part of the name, not a
    place: "Aljunied" in "Ridzwan Aljunied" is a surname. A name that reads as a street ("Jalan
    Membina", "Bedok North Street") does not count."""
    # a name span is compared after its lower-case edges are trimmed: "kat Sengkang" is a place
    names = [
        t for t in (_trim_name(h) for h in hits if h.category == "NAME") if not _street_like(t.text)
    ]
    return [
        h
        for h in hits
        if not (
            h.category == "ESTATE"
            and any(
                n.start <= h.start and h.end <= n.end and n.end - n.start > h.end - h.start
                for n in names
            )
        )
    ]


_SCHOOL_WORD = re.compile(
    r"\b(?:school|primary|secondary|college|polytechnic|poly|ITE|institute|academy|kindergarten"
    r"|university|JC|madrasah|preschool|pre-school)\b",
    re.IGNORECASE,
)
_FACILITY_WORD = re.compile(
    r"\b(?:centre|center|home|shelter|hospital|clinic|polyclinic|hostel|residence)\b",
    re.IGNORECASE,
)


def _relabel_schools(hits: list[Hit]) -> list[Hit]:
    """A zero-shot SCHOOL span with no school word ("Kopi Corner Cafe") is an employer, or a
    facility when it names a centre or a home: as a school it would take an invented polytechnic's
    name."""
    out = []
    for h in hits:
        if h.category == "SCHOOL" and not _SCHOOL_WORD.search(h.text):
            cat = "FACILITY" if _FACILITY_WORD.search(h.text) else "EMPLOYER"
            h = Hit(h.start, h.end, h.text, cat, h.detector, h.score)
        out.append(h)
    return out


def _places_inside_employers(hits: list[Hit]) -> list[Hit]:
    """A mall inside a longer employer phrase ("a retail outlet at Northpoint City") is part of the
    workplace, which is withheld or generalised as a whole."""
    emps = [h for h in hits if h.category == "EMPLOYER"]
    return [
        h
        for h in hits
        if not (
            h.detector == "gazetteer.place"
            and any(
                e.start <= h.start and h.end <= e.end and e.end - e.start > h.end - h.start
                for e in emps
            )
        )
    ]


def _estates_inside_orgs(hits: list[Hit]) -> list[Hit]:
    """An estate at the end of a longer organisation name ("Tampines" in "Ace Hardware Tampines")
    is part of that name. Left to win on trust, the estate would be generalised and the rest of the
    name ("Ace Hardware") would cross as written."""
    orgs = [h for h in hits if h.category in {"EMPLOYER", "FACILITY", "SCHOOL"}]

    def inside(e: Hit) -> bool:
        for o in orgs:
            if o.start < e.start and e.end <= o.end:
                head = o.text[: e.start - o.start].split()
                if (
                    head
                    and all(w[:1].isupper() or w[:1].isdigit() for w in head)
                    # "HDB Choa Chu Kang" is an agency's branch in the estate: the estate stays
                    and " ".join(head).lower() not in AGENCY_STOPLIST
                ):
                    return True
        return False

    return [h for h in hits if not (h.category == "ESTATE" and inside(h))]


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
                    name = text[h.start : end]
                    # "Bukit Merah Secondary School" is a school, generalised by its level
                    school = re.search(
                        r"\b(?:Primary|Secondary)\s+School\b|\bSchool\b|\bJunior College\b"
                        r"|\bPolytechnic\b",
                        name,
                    )
                    cat = "SCHOOL" if school else "FACILITY"
                    out.append(Hit(h.start, end, name, cat, "gazetteer.org", 0.9))
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


# Shared public spaces that a zero-shot model sometimes tags as an employer.
_COMMON_PLACE = re.compile(
    r"(?:the\s+|a\s+)?(?:void deck|lift lobby|corridor|playground|staircase|multi-storey car park"
    r"|community centre|residents'? (?:committee|corner|network centre)|RC|market|wet market"
    r"|hawker centre|park|mosque|church|temple|library)s?",
    re.IGNORECASE,
)
_CURRENT_YEAR = __import__("datetime").date.today().year
_TRUST = {"sg": 3, "gazetteer": 3, "propagate": 2, "gliner": 1, "presidio": 0}


def _trust(h: Hit) -> int:
    return _TRUST.get(h.detector.split(".")[0], 1)


def _sane(h: Hit) -> bool:
    t = h.text.strip()
    core = re.sub(r"^the\s+", "", re.sub(r"[^\w/& ]", "", t).lower())
    if h.category in {"NAME", "EMPLOYER", "FACILITY"} and core in COMMON_NOUNS:
        return False
    if h.category == "NAME" and core in COMMON_WORKPLACES:
        return False
    if h.category in {"EMPLOYER", "FACILITY", "ESTATE", "NAME"} and (
        core in AGENCY_STOPLIST
        or core.replace(" ", "") in {a.replace(" ", "") for a in AGENCY_STOPLIST}
    ):
        return False
    if h.category in {"EMPLOYER", "FACILITY", "ESTATE"} and _TITLE_PREFIX.match(t):
        return False
    if h.category in {"EMPLOYER", "FACILITY"} and re.match(
        r"(?:the\s+)?(?:Department|Dept\.?)\s+of\s+[A-Z]", t
    ):
        return False  # a hospital department is part of a public body, not an employer
    if h.category == "EMPLOYER" and _COMMON_PLACE.fullmatch(t):
        return False  # "the void deck": a shared space under an HDB block, not an employer
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
    if h.category == "NRIC" and not re.fullmatch(r"[STFGMstfgm][ \t-]?\d{7}[ \t-]?[A-Za-z]", t):
        return False
    if h.category == "NAME" and _street_like(t):
        return False  # "Jalan Membina": a street, never a person
    if h.category == "NAME" and _TITLE_PREFIX.sub("", t).strip().lower() in ROLE_WORDS:
        return False
    if h.category == "NAME" and t.lower() in KIN_PHRASES:
        return False
    if h.category == "NAME" and t.split()[0].isupper() and t.split()[0].lower() in AGENCY_STOPLIST:
        return False  # "MOE SSW": an agency acronym and a role, not a person
    if h.category == "NAME" and any(
        w in ROLE_WORDS for w in re.split(r"\s+", _TITLE_PREFIX.sub("", t).lower())[:1]
    ):
        return False  # "Ward 9B", "Son says": the first token names a role or a place, not a person
    if h.category in {"FACILITY", "SCHOOL"} and not any(c.isupper() for c in t):
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
    # A one-letter slip in a name token of five or more letters ("Suriaty" for "Suriati") is the
    # same name.
    from socareguard.outbound.surrogates import name_variant

    long_toks = {t for t in tokens if len(t) >= 5}
    for m in re.finditer(r"(?<![\w-])[A-Z][a-z]{4,}(?![\w-])", text):
        w = m.group(0)
        if (
            w in tokens
            or w.lower() in ROLE_WORDS
            or w.lower() in AGENCY_STOPLIST
            or w.lower() in _NOT_NAMES
            or any(k.start <= m.start() and m.end() <= k.end for k in hits + out)
        ):
            continue
        if any(name_variant(w, t) for t in long_toks):
            out.append(Hit(m.start(), m.end(), w, "NAME", "propagate", 0.7))
    return out


# Capitalised words a one-letter slip could turn a name into, that are not names.
_NOT_NAMES = {
    "january", "february", "march", "april", "june", "july", "august", "september", "october",
    "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "singapore", "assessment", "presenting", "observations", "strengths", "summary",
}  # fmt: skip


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


# Lower-case words that may sit inside a name ("Nur binti Ali", "Anand s/o Raju", "van der Berg").
_NAME_PARTICLES = _LINK_WORDS | {"van", "der", "de", "da", "di", "dos", "del", "la", "le", "von"}


def _trim_name(h: Hit) -> Hit:
    """Drop lower-case words at either edge of a NAME span: a NER model reading Malay or Singlish
    returns "Ahmad kena", "kat Sengkang" or "Mak dia", and only the capitalised words can be a
    name. A span left with no word is returned unchanged for _sane to reject."""
    if h.category != "NAME":
        return h
    toks = list(re.finditer(r"\S+", h.text))
    i, j = 0, len(toks)
    while i < j and toks[i].group(0).islower() and toks[i].group(0) not in _NAME_PARTICLES:
        i += 1
    # a lower-case word at the end, a dangling link word ("Ahmad bin") included; a capitalised
    # "Le" or "Da" is a name token ("Jia Le") and stays
    while j > i and toks[j - 1].group(0).islower():
        j -= 1
    # a possessive is not part of the name: "Wei Ming's" is "Wei Ming", the same person
    last = toks[j - 1].group(0) if j > i else ""
    if last.endswith(("'s", "\u2019s")) and len(last) > 2:
        s, e = toks[i].start(), toks[j - 1].end() - 2
        return Hit(h.start + s, h.start + e, h.text[s:e], h.category, h.detector, h.score)
    if i == 0 and j == len(toks):
        return h
    if i >= j:
        return Hit(h.start, h.start, "", h.category, h.detector, h.score)
    s, e = toks[i].start(), toks[j - 1].end()
    return Hit(h.start + s, h.start + e, h.text[s:e], h.category, h.detector, h.score)


def _resolve(hits: list[Hit]) -> list[Hit]:
    hits = [_trim_leading(_trim_name(h)) for h in hits if h.category != "DATE"]
    hits = [h for h in hits if h.text and _sane(h)]
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


# A safety plan names a safety measure. A zero-shot span without one ("review in two weeks" at the
# end of a routine plan) is a routine detail, and withholding it loses the plan's timing.
_SAFETY_CUE = re.compile(
    r"\b(?:safe\w*|plan\w*|code[- ]?words?|exit|escape|refuge|shelter|hid(?:e|es|ing)|go[- ]bag"
    r"|packed bag|spare (?:set of )?keys?|emergency|999|hotline|police|lock\w*|run|flee\w*"
    r"|pins?|passwords?|bank\w*|withdraw\w*|limits?|alone|block\w*|avoid\w*|meet|route|change\w*"
    r"|protect\w*|risk)\b",
    re.IGNORECASE,
)


def _safety_plans_with_cue(hits: list[Hit]) -> list[Hit]:
    return [h for h in hits if h.category != "ATTR:safety_plan" or _SAFETY_CUE.search(h.text)]


def _merge_attributes(hits: list[Hit]) -> list[Hit]:
    """Overlapping attribute hits of the same key collapse to the longest. Different keys may overlap."""
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
    hits = _places_inside_employers(
        _estates_inside_orgs(
            _estates_outside_names(_relabel_schools([h for h in hits if h.score >= min_score]))
        )
    )
    ents = _resolve(_estate_in_org_name(text, hits))
    ents = _resolve(_extend_names(text, ents))
    ents = _resolve(ents + _propagate_names(text, ents))
    ents = _merge_addresses(text, ents)
    attrs = _safety_plans_with_cue(attrs)
    return Detection(entities=ents, attributes=sorted(attrs, key=lambda h: h.start), detectors=used)
