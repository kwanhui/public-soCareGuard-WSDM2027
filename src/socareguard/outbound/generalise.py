"""Sensitive-attribute and quasi-identifier generalisation.

This is an operation distinct from entity substitution: the span is replaced by a banded or
categorical form that keeps what the drafting task needs (that a disclosure happened, that a
protection order is pending, an age band, a school level) and drops what re-identifies in a
small jurisdiction. Rules come from the policy pack, and the lexicons here are the mapping tables.
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
            r"cerebral palsy|wheelchair|amput|spinal|paraple|quadriple|mobility|muscular|stroke|hemipleg"
            r"|pares[ie]s",
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
        re.compile(
            r"theft|shop ?lift|steal|stole|burglar|vandal|mischief|property|trespass", re.IGNORECASE
        ),
        "a property offence",
    ),
    (
        re.compile(r"unlawful assembly|public nuisance|disorderly", re.IGNORECASE),
        "a public order offence",
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


# A long clause keeps its sentence only when every phrase naming the condition or offence can be
# replaced as a whole noun phrase, article and modifiers included, where a noun phrase reads
# correctly; otherwise the caller falls back to the whole-clause statement. Each entry is
# (phrase, label), longer forms first; the patterns above still pick the whole-clause label.
_DISABILITY_PHRASES: list[tuple[str, str]] = [
    (
        (
            r"intellectual developmental disorder|developmental disorder"
            r"|(?:intellectual|learning|developmental)[ -](?:disabilit(?:y|ies)|delay|impairment)"
            r"|global developmental delay|down(?:'s)? syndrome"
            r"|autism(?:\s+spectrum)?(?:\s+(?:disorder|condition))?|asd|adhd"
            r"|attention[- ]deficit(?:[/ -]hyperactivity)?\s+disorder"
        ),
        "a developmental disability",
    ),
    (
        (
            r"cerebral palsy|spinal(?:\s+cord)?\s+injury|(?:para|quadri|tetra|hemi)plegia"
            r"|muscular dystrophy|amputation|stroke|physical disabilit(?:y|ies)"
            r"|mobility (?:impairment|disability|limitation)s?"
        ),
        "a physical disability",
    ),
    (
        (
            r"schizophrenia|schizoaffective disorder|bipolar(?:\s+(?:affective\s+)?disorder)?"
            r"|major depressive disorder|depressive disorder|depression"
            r"|(?:generali[sz]ed\s+)?anxiety(?:\s+disorder)?"
            r"|psychiatric (?:disabilit(?:y|ies)|condition|illness|disorder|diagnosis)"
            r"|mental health[- ]related (?:disability|condition)"
            r"|mental (?:health (?:condition|issues?|disorder)|illness)|psychosis|psychotic disorder"
            r"|ocd|obsessive[- ]compulsive disorder|ptsd|post[- ]traumatic stress disorder"
        ),
        "a psychiatric condition",
    ),
    (
        (
            r"epilepsy|seizure disorder|seizures|brain injury|dementia|parkinson'?s(?: disease)?"
            r"|neurological (?:condition|disorder)"
        ),
        "a neurological condition",
    ),
    (
        (
            r"blindness|visual impairment|low vision|deafness|hearing (?:loss|impairment)"
            r"|sensory (?:disabilit(?:y|ies)|impairment)"
        ),
        "a sensory disability",
    ),
    # An aid names the need rather than the diagnosis, and stays a noun the sentence can hold.
    (
        (
            r"(?:(?:power(?:ed)?|manual|motori[sz]ed|electric)\s+)?wheelchair"
            r"|walking (?:frame|aid|stick)|walker|mobility (?:aid|scooter|device)"
        ),
        "a mobility aid",
    ),
    (r"white cane|hearing aids?", "an assistive device"),
]
_DISABILITY_ADJECTIVES: list[tuple[str, str]] = [
    (r"autistic", "a developmental disability"),
    (
        r"(?:para|quadri|tetra|hemi)plegic|wheelchair[- ](?:bound|dependent)",
        "a physical disability",
    ),
    (r"epileptic", "a neurological condition"),
    (r"blind|deaf|visually impaired|hearing[- ]impaired|partially sighted", "a sensory disability"),
]
_DISABILITY_MODIFIERS = (
    r"mild|moderate|severe|profound|borderline|spastic|long-standing|longstanding|chronic"
    r"|acquired|traumatic|post-traumatic|post-acute|early-onset|late-onset|mixed|significant"
    r"|lifelong|congenital|underlying|known|diagnosed|identified|established|documented"
    r"|confirmed|formal|lower-limb|upper-limb|mild-to-moderate"
)
_OFFENCE_PHRASES: list[tuple[str, str]] = [
    (
        (
            r"(?:theft|property|shop[- ]?theft)[- ]related|property (?:offen[cs]es?|crimes?|damage)"
            r"|(?:shop[- ]?)?theft|shop ?lifting|stealing|burglary|house-?breaking|vandalism|mischief"
            r"|(?:criminal )?trespass"
        ),
        "a property offence",
    ),
    (
        r"unlawful assembly|public nuisance|disorderly (?:behaviou?r|conduct)",
        "a public order offence",
    ),
    (r"vaping|e-cigarettes?|smoking", "a tobacco or vaping matter"),
    (
        (
            r"drug[- ]related|drug (?:offen[cs]es?|use|possession|trafficking|consumption|abuse)"
            r"|cannabis|inhalant (?:abuse|use)|substance (?:misuse|abuse)|controlled drugs?"
        ),
        "a drug-related offence",
    ),
    (
        (
            r"assault[- ]related|rioting|riot|assault|fighting|(?:physical )?fights?|affray|robbery"
            r"|violent (?:offen[cs]es?|crimes?|behaviou?r)|weapons? offen[cs]es?"
            r"|(?:voluntarily )?causing hurt"
        ),
        "an offence involving violence",
    ),
    (r"truancy|truanting|unauthori[sz]ed absences?", "a school attendance matter"),
    (r"cheating|scams?|fraud|forgery", "a dishonesty offence"),
]
_OFFENCE_MODIFIERS = (
    r"non-?violent|minor|petty|serious|repeated|youth|juvenile|peer-influenced|group|school"
)
# Qualifiers that change what the sentence asserts are kept in front of the label.
_KEPT_MODIFIERS = {"alleged", "suspected", "attempted", "possible"}
# Nouns after an offence phrase: "offence" folds into the label; the others keep their place and
# take the label as their object ("a charge involving a property offence").
_OFFENCE_HEADS = r"offen[cs]es?|charges?|matters?|incidents?|cases?|allegations?|activit(?:y|ies)"
# A noun phrase without an article reads correctly after these words or after punctuation.
_NP_CONTEXT = {
    "for",
    "with",
    "of",
    "in",
    "after",
    "following",
    "regarding",
    "about",
    "involving",
    "re:",
    "and",
    "or",
    "over",
    "into",
    "by",
    "to",
    "from",
    "has",
    "have",
    "had",
    "including",
    "include",
    "includes",
    "involves",
    "involved",
    "as",
    "given",
    "on",
    "despite",
    "concerning",
    "since",
    "requiring",
    "requires",
    "require",
    "uses",
    "using",
    "use",
    "needs",
    "need",
    "at",
    "under",
}
# Words the category patterns match that name no condition or offence on their own.
_BENIGN = {
    "mobility",
    "property",
    "hearing",
    "visual",
    "absent",
    "absence",
    "substance",
    "controlled",
    "non-violent",
    "nonviolent",
    "violence",
    "offence",
}
_DETERMINER = (
    r"(?P<det>\b(?:a|an|the|his|her|their|its|my|our)\s+"
    r"|\b(?!(?:it|he|she|that|what|there|who|here)'s\b)[\w-]+'s\s+)?"
)


def _soften(
    text: str,
    table: list[tuple[re.Pattern[str], str]],
    phrases: list[tuple[str, str]],
    modifiers: str,
    heads: str = "",
    adjectives: list[tuple[str, str]] | None = None,
    strict: bool = True,
) -> str | None:
    """Keep the sentence and replace each phrase naming the offence or condition by its category.

    Returns None when no clean in-place rewrite exists: a word naming the condition or offence
    would remain, or its replacement would not read as a noun phrase. With ``strict`` false the
    phrases that can be replaced are replaced and the rest of the sentence stays as written."""
    labels: list[str] = []

    def hold(phrase: str) -> str:
        labels.append(phrase)
        return f"\x00{len(labels) - 1}\x00"

    mods = rf"(?:(?:{modifiers}|{'|'.join(_KEPT_MODIFIERS)})[\s,]+)*"
    out = text
    # "is blind" -> "has a sensory disability"; an adjective before a noun ("an autistic son")
    # has no clean rewrite and is left for the residue check.
    have = {"is": "has", "are": "have", "was": "had", "were": "had"}
    for adj, lab in adjectives or []:
        out = re.sub(
            rf"\b(is|are|was|were)\s+{mods}(?:{adj})\b"
            r"(?=\s*(?:[,.;:)]|$)|\s+(?:and|or|but|since|with|from|due|after|following|in|at|for)\b)",
            lambda m, lab=lab: hold(f"{have[m.group(1).lower()]} {lab}"),
            out,
            flags=re.IGNORECASE,
        )
    core = "|".join(f"(?P<c{i}>{p})" for i, (p, _) in enumerate(phrases))
    head = rf"(?:\s+(?P<head>{heads}))?" if heads else ""
    pat = re.compile(
        # "an offence of shop theft" is one phrase; so is a trailing "(mild)" or "(ABI)"
        rf"(?P<pre>\b(?:an?\s+)?(?:alleged\s+)?offen[cs]es?\s+(?:of|involving)\s+)?"
        rf"{_DETERMINER}(?P<mods>{mods})(?<![\w-])(?:{core})\b{head}"
        r"(?:\s*\((?:mild|moderate|severe|[A-Z]{2,6})\))?",
        re.IGNORECASE,
    )

    def sub(m: re.Match[str]) -> str:
        det = (m.group("det") or "").strip()
        if m.group("pre"):
            det = ""
        before = out[: m.start()].rstrip()
        prev = before.rsplit(None, 1)[-1].lower() if before else ""
        if not det and prev and prev not in _NP_CONTEXT and before[-1] not in ":;,(-\n\x00":
            return m.group(0)  # "caught vaping", "these fights": not a noun-phrase position
        label = next(lab for i, (_, lab) in enumerate(phrases) if m.group(f"c{i}"))
        art, noun = label.split(" ", 1)
        kept = [
            w.lower()
            for w in re.split(r"[\s,]+", (m.group("pre") or "") + m.group("mods"))
            if w.lower() in _KEPT_MODIFIERS
        ]
        h = (m.groupdict().get("head") or "").lower()
        if h and not h.startswith("offen"):
            noun = f"{h} involving {label}"
            art = "" if h.endswith("s") and not det else "a"
        noun = " ".join([*kept, noun])
        if art in {"a", "an"}:
            art = _article(noun)
        if det.lower() not in {"", "a", "an"}:
            art = det
        elif not det and _NOUN_AFTER.match(out[m.end() :]):
            art = ""  # a noun modifier: "wheelchair funding" -> "mobility aid funding"
        phrase = f"{art} {noun}".strip()
        if not before or before[-1] in ".!?":
            phrase = phrase[0].upper() + phrase[1:]
        return hold(phrase)

    out = pat.sub(sub, out)
    masked = re.sub(r"\x00\d+\x00", " ", out)
    for p, _ in table if strict else []:
        for m in re.finditer(rf"\b[\w'-]*(?:{p.pattern})[\w'-]*\b", masked, re.IGNORECASE):
            if m.group(0).lower() not in _BENIGN:
                return None

    # "accused of shop theft and minor vandalism" names one category twice: say it once
    def once(m: re.Match[str]) -> str:
        same = labels[int(m.group(1))].lower() == labels[int(m.group(3))].lower()
        return f"\x00{m.group(1)}\x00" if same else m.group(0)

    out = re.sub(r"\x00(\d+)\x00(,? (?:and|or) |, )\x00(\d+)\x00", once, out)
    return re.sub(r"\x00(\d+)\x00", lambda m: labels[int(m.group(1))], out)


# A head noun right after a condition or aid makes it a modifier, which takes no article.
_NOUN_AFTER = re.compile(
    r"\s+(?:funding|support|needs|assessment|user|users|access|services?|care|training"
    r"|programme|program|subsidy|grant|review|clinic|team|equipment)\b",
    re.IGNORECASE,
)


def _article(noun: str) -> str:
    return "an" if noun[:1].lower() in "aeiou" else "a"


_ORDER_TERM = re.compile(
    r"(?P<art>\ban\s+)?\b(?:personal protection order|PPO|expedited order|domestic exclusion order"
    r"|DEO)\b(?!/)(?:\s*\((?:PPO|DEO)\))?"
    r"(?:(?P<mid>[^.;\n]{0,25}?)\s+(?:on|dated|until|from)\s+"
    r"(?:\d{1,2}\s+[A-Z][a-z]+(?:\s+\d{4})?|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b)?",
    re.IGNORECASE,
)


def _generalise_order_terms(text: str) -> str:
    """Name any order type as "protection order" and drop its dates, keeping the sentence:
    "applying for a PPO" -> "applying for a protection order", "an expedited order in force
    until 26 Sep" -> "a protection order in force"."""
    text = re.sub(r"(?i)\bprotection order\s*\((?:PPO|DEO)\)", "protection order", text)

    def sub(m: re.Match[str]) -> str:
        return ("a " if m.group("art") else "") + "protection order" + (m.group("mid") or "")

    return _ORDER_TERM.sub(sub, text)


_ORDER_WORD = re.compile(
    r"\b(?:PPO|personal protection order|protection order|expedited order|domestic exclusion order"
    r"|DEO)\b",
    re.IGNORECASE,
)
_DATE = (
    r"(?:\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?(?:\s+\d{4})?"
    r"|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b"
)
_VENUE = r"(?:the\s+)?(?:Family Justice Courts?|FJC|State Courts?|Syariah Court|Youth Court)"
_HEARING_PHRASE = re.compile(
    rf"(?:,\s*|\s+)(?:with\s+|and\s+)?(?:a\s+|the\s+|her\s+|his\s+)?(?:next\s+)?(?:court\s+)?"
    rf"(?:hearing|mention)\b[^.;,\n]{{0,60}}?(?:{_DATE}|{_VENUE}\b)"
    rf"(?:\s+(?:on|at|in|before)\s+(?:{_DATE}|{_VENUE}\b))*",
    re.IGNORECASE,
)
_DATE_PHRASE = re.compile(
    rf"\s*,?\s+(?:on|dated|until|from|by|since|for|set for|fixed for|scheduled for)\s+{_DATE}"
    rf"|\s+{_DATE}",
    re.IGNORECASE,
)
_VENUE_PHRASE = re.compile(rf"\s+(?:at|in|before)\s+{_VENUE}\b", re.IGNORECASE)
# A hearing or mention with a date, a court or a venue: the only clause without an order word that
# the protection-order rule may rewrite.
_HEARING_CUE = re.compile(
    rf"\b(?:hearing|mention)\b[^.;\n]{{0,60}}?(?:{_DATE}|{_VENUE}\b|\bcourts?\b|\bdate\b)",
    re.IGNORECASE,
)


def _drop_court_specifics(text: str) -> str:
    """Remove a hearing phrase that carries a date or venue, then any remaining date or court
    venue: a protection order's status may leave, its dates and place may not."""

    def hearing(m: re.Match[str]) -> str:
        # "the protection order mention at the FJC on 12/9" keeps "hearing" after the order
        before = text[: m.start()]
        return " hearing" if re.search(r"protection order$", before, re.IGNORECASE) else ""

    text = _HEARING_PHRASE.sub(hearing, text)
    text = _DATE_PHRASE.sub("", text)
    return _VENUE_PHRASE.sub("", text)


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


# Public hospitals and national centres are public bodies: their names identify no one, a referral
# or an appointment needs them, and the corpus keeps them as real names (corpus/README.md).
PUBLIC_HOSPITALS = {
    "tan tock seng hospital", "singapore general hospital", "national university hospital",
    "changi general hospital", "khoo teck puat hospital", "ng teng fong general hospital",
    "sengkang general hospital", "alexandra hospital", "kk women's and children's hospital",
    "kk women's & children's hospital", "institute of mental health", "woodlands hospital",
    "jurong community hospital", "outram community hospital", "sengkang community hospital",
    "yishun community hospital", "national cancer centre singapore", "national heart centre singapore",
    "national neuroscience institute", "national skin centre", "national university cancer institute",
}  # fmt: skip


def is_public_body(text: str, towns: set[str] | frozenset[str] = frozenset()) -> bool:
    """A named public hospital, or a polyclinic named after its town ("Bedok Polyclinic")."""
    t = re.sub(r"^the\s+", "", text.strip().lower()).replace("\u2019", "'")
    if t in PUBLIC_HOSPITALS:
        return True
    m = re.fullmatch(r"(.+?)\s+polyclinic", t)
    return bool(m and m.group(1) in {x.lower() for x in towns})


# Shopping malls and shared places are places, not organisations: a mall named in a note leaves as
# its kind, never as an invented company name ("Compass One" -> "Wrenhaven Services").
MALLS = {
    "compass one", "jurong point", "bugis junction", "bugis+", "northpoint city", "northpoint",
    "causeway point", "tampines mall", "tampines 1", "century square", "bedok mall",
    "waterway point", "hougang mall", "heartland mall", "nex", "junction 8", "amk hub",
    "vivocity", "plaza singapura", "ion orchard", "westgate", "jem", "imm", "lot one", "sun plaza",
    "rivervale mall", "seletar mall", "sengkang grand mall", "punggol plaza", "parkway parade",
    "white sands", "loyang point", "changi city point", "jewel changi airport",
    "clementi mall", "the clementi mall", "west mall", "bukit panjang plaza", "hillion mall",
    "yew tee point", "kallang wave mall", "city square mall", "admiralty place", "canberra plaza",
    "sembawang shopping centre", "woodlands north plaza", "marsiling mall", "toa payoh hub",
    "ang mo kio hub", "oasis terraces", "our tampines hub", "bukit timah plaza", "tiong bahru plaza",
    "west coast plaza", "anchorpoint", "queensway shopping centre", "pasir ris mall",
    "downtown east", "white sands mall", "eastpoint mall", "tampines west",
}  # fmt: skip
# the kind word ends the name: "Tampines Mall" is a mall, "mall security" is a role
_PLACE_KIND = re.compile(
    r"\b(?:(?:mall|plaza|shopping cent(?:re|er)|hub)|(?P<hawker>hawker cent(?:re|er)|food cent(?:re|er)"
    r"|food court|market)|(?P<kopi>kopitiam|coffee ?shop))s?$",
    re.IGNORECASE,
)


def shared_place(text: str) -> str | None:
    """The kind of a shared place a span names ("a shopping mall", "a hawker centre"), or None."""
    t = re.sub(r"^the\s+", "", text.strip().lower()).replace("\u2019", "'")
    if t in MALLS:
        return "a shopping mall"
    m = _PLACE_KIND.search(t)
    if not m:
        return None
    if m.group("hawker"):
        return "a hawker centre" if "market" not in m.group(0).lower() else "a market"
    if m.group("kopi"):
        return "a coffee shop"
    return "a shopping mall"


_YOUTH_FACILITY = re.compile(
    r"\byouth\b|boys'|girls'|boys\u2019|girls\u2019|juvenile|pertapis|centre for youth",
    re.IGNORECASE,
)
_CARE_FACILITY = re.compile(
    r"\b(?:home|homes|nursing|eldercare|elder care|aged care|hospice|residence|residential"
    r"|welfare|sheltered|care centre|community hospital|step-down|rehabilitation)\b",
    re.IGNORECASE,
)


def generalise_facility(text: str) -> str:
    """A place's kind, never its name. A school keeps its level; a home is a youth facility only
    when its name says so, and otherwise a care facility."""
    t = text.lower()
    if re.search(r"\bschool\b|\bjunior college\b|\bpolytechnic\b|\bite college\b", t):
        return generalise_school(text)
    if "shelter" in t or "harapan" in t or "teduh" in t or "haven" in t:
        return "a crisis shelter"
    if "day activity" in t or re.search(r"\bdac\b", t):
        return "a day activity centre"
    if "hospital" in t or "institute of mental health" in t or re.search(r"\bimh\b", t):
        return "a hospital"
    if "polyclinic" in t or "clinic" in t:
        return "a clinic"
    if (
        re.search(r"\bfsc\b", t)
        or "family service" in t
        or "care corner" in t
        or "fei yue" in t
        or "montfort" in t
    ):
        return "a family service centre"
    if _YOUTH_FACILITY.search(text):
        return "a youth residential facility"
    if _CARE_FACILITY.search(text):
        return "a care facility"
    return "a service provider"


def generalise_employer(text: str) -> str:
    return "an employer"


# Where a short diagnosis span sits in its sentence decides the form of its replacement.
_POSSESSIVE = {"his", "her", "their", "its", "my", "our", "your"}
_ARTICLES = {"a", "an", "the"}
_COPULA = {"is", "are", "was", "were", "be", "been", "being"}
_SUBJECTS = {
    "she", "he", "they", "client", "patient", "son", "daughter", "mother", "father", "husband",
    "wife", "child", "sibling", "brother", "sister", "grandmother", "grandfather", "caregiver",
}  # fmt: skip
# Words between a preposition and the condition that a noun phrase can keep ("with a resulting
# physical disability"), and words that describe the condition and are dropped with it.
KEPT_NP_MODIFIERS = {
    "resulting", "associated", "secondary", "residual", "subsequent", "suspected", "possible",
    "new", "recent", "chronic", "underlying", "related", "ongoing",
}  # fmt: skip
DROPPED_NP_MODIFIERS = {
    "left", "right", "bilateral", "mild", "moderate", "severe", "partial", "complete", "acute",
    "left-sided", "right-sided",
}  # fmt: skip


def grammar_slot(before: str) -> str:
    """The grammatical slot a short diagnosis span fills, from the words before it: "np" after a
    preposition, an article, a verb that takes an object or a punctuation mark; "bare" after a
    possessive; "pred" after a subject; "cop" after a form of "to be"; "clause" at the start of a
    sentence (the span is a statement of its own); "none" when no replacement fits."""
    head = before.rstrip()
    if not head or head[-1] in ".!?\n":
        return "clause"
    if head[-1] in ":;,(-":
        return "np"
    prev = re.split(r"\s+", head)[-1]
    low = prev.lower()
    if low in _POSSESSIVE or low.endswith(("'s", "\u2019s")):
        return "bare"
    if low in _NP_CONTEXT or low in _ARTICLES:
        return "np"
    if low in _COPULA:
        return "cop"
    if low in _SUBJECTS or (prev[:1].isupper() and prev.isalpha()):
        return "pred"
    return "none"


def _short_diagnosis(t: str, label: str | None, before: str) -> str:
    label = label or "a health condition"
    slot = grammar_slot(before)
    noun = label.split(" ", 1)[1]
    if slot in ("np", "bare"):
        kept = [w.lower() for w in t.split()[:3] if w.lower() in KEPT_NP_MODIFIERS]
        noun = " ".join([*kept, noun])
        return noun if slot == "bare" else f"{_article(noun)} {noun}"
    if slot == "cop":
        return f"living with {label}"
    # a subject before the span, a statement of its own, or (after the caller's clause fallback)
    # the whole clause: the span becomes a predicate
    return f"has {label}"


# A sentence that opens with a section label, or whose subject is the practitioner or the agency,
# is the practitioner's own account of what to do. A rule may replace a phrase naming a condition
# or an offence inside it, but never removes or restates the sentence as a whole: a plan that
# leaves as "Has a psychiatric condition." invites the model to write a plan of its own.
SECTION_LABEL = re.compile(
    r"^\s*(?:Plan|Assessment|Next steps?|Recommendations?|Impressions?|Actions?|Action plan"
    r"|Follow[- ]up|Intervention|Goals?)\b[^:\n.]{0,40}:",
    re.IGNORECASE,
)
# The practitioner or the agency as the subject of an action ("I will refer", "SW to follow up",
# "the centre has arranged"): a sentence about what the practitioner does. "I note acquired brain
# injury" states the client's condition, so observing verbs are not in the list.
_ACTION = (
    r"(?:will|shall|would|to|plans?|planned|intends?|recommends?|recommended|proposes?|refers?"
    r"|referred|arranged|arranges?|advised|explained|discussed|followed up|follows? up"
    r"|(?:am|are|is|has|have|had) (?:going to|referring|arranging|recommending|referred|arranged"
    r"|advised|explained|discussed|followed up))"
)
_PRACTITIONER_SUBJECT = re.compile(
    rf"^\s*(?:(?:I|We)\s+{_ACTION}\b"
    r"|(?i:(?:the\s+|our\s+|this\s+)?(?:worker|social worker|case ?worker|case manager|practitioner"
    r"|probation officer|officer|writer|SW|MSW|FSW|PO|centre|center|agency|team|FSC|office)"
    rf"\s+{_ACTION}\b))"
)


def soften_in_place(key: str, text: str) -> str:
    """Replace only the phrases that name a condition or an offence, leaving the rest of the
    clause (and the names in it) as written."""
    if key == "offence":
        out = _soften(
            text,
            OFFENCE_CATEGORIES,
            _OFFENCE_PHRASES,
            _OFFENCE_MODIFIERS,
            _OFFENCE_HEADS,
            strict=False,
        )
    else:
        out = _soften(
            text,
            DISABILITY_CATEGORIES,
            _DISABILITY_PHRASES,
            _DISABILITY_MODIFIERS,
            adjectives=_DISABILITY_ADJECTIVES,
            strict=False,
        )
    return out if out is not None else text


# A plan label, as distinct from an assessment label: what follows it is what the practitioner
# will do, and no rule restates it.
PLAN_LABEL = re.compile(
    r"^\s*(?:Plan|Next steps?|Recommendations?|Actions?|Action plan|Actions and plan|Follow[- ]up"
    r"|Intervention|Goals?)\b[^:\n.]{0,40}:",
    re.IGNORECASE,
)
# A plan item: an imperative verb after an optional list marker ("1) Arrange formal capacity
# assessment", "- Refer for counselling").
_PLAN_ITEM = re.compile(
    r"^\s*(?:(?:\d{1,2}|[a-z])[.)]\s*|[-\u2022*]\s*)?(?:Arrange|Refer|Submit|Follow up|Review|Monitor"
    r"|Continue|Liaise|Schedule|Contact|Complete|Obtain|Discuss|Convene|Explore|Provide|Request"
    r"|Coordinate|Link|Assist|Support|Apply|Update|Check|Confirm|Consider|Plan|Seek|Encourage)\b"
)


def _sentence(before: str, text: str) -> str:
    head = re.split(r"(?<=[.!?])\s+|\n", before)[-1] if before else ""
    return head + text


def plan_sentence(before: str, text: str) -> bool:
    """Whether ``text`` sits in a plan: a sentence after a plan label, a plan item, or a sentence
    whose subject is the practitioner or the agency doing something. No rule restates it."""
    sentence = _sentence(before, text)
    return bool(
        PLAN_LABEL.match(sentence)
        or _PRACTITIONER_SUBJECT.match(sentence)
        or _PLAN_ITEM.match(sentence)
    )


def practitioner_sentence(before: str, text: str) -> bool:
    """Whether ``text``, preceded by ``before``, sits in a sentence that opens with a section label
    (an assessment or an impression included) or in a plan."""
    return bool(SECTION_LABEL.match(_sentence(before, text)) or plan_sentence(before, text))


def generalise_attribute(
    key: str,
    text: str,
    rule: str,
    pack_id: str,
    client_gender_hint: str | None = None,
    before: str = "",
    note: str = "",
) -> str:
    """Apply a pack rule to an attribute span. Returns the outbound text. ``before`` is the text
    that precedes the span; a short diagnosis span takes the form that fits it. ``note`` is the
    whole message, which the capacity rule reads for a finding or a proxy consent elsewhere."""
    t = text.strip()
    if rule == "redact":
        return "[safety plan withheld from this draft]" if key == "safety_plan" else "[withheld]"
    if rule == "category":
        table = DISABILITY_CATEGORIES if key in {"disability", "diagnosis"} else OFFENCE_CATEGORIES
        if practitioner_sentence(before, text):
            # only the phrase naming the condition or the offence is replaced, in place
            if key == "offence":
                return (
                    _soften(
                        t, table, _OFFENCE_PHRASES, _OFFENCE_MODIFIERS, _OFFENCE_HEADS, strict=False
                    )
                    or t
                )
            return (
                _soften(
                    t,
                    table,
                    _DISABILITY_PHRASES,
                    _DISABILITY_MODIFIERS,
                    adjectives=_DISABILITY_ADJECTIVES,
                    strict=False,
                )
                or t
            )
        # "non-violent" names no violence
        label = next(
            (lab for pat, lab in table if pat.search(re.sub(r"(?i)\bnon-?violent\b", "", t))), None
        )
        if (
            key != "offence"
            and label is None
            and not _names_condition(t)
            and _caregiver_sentence(before, t)
        ):
            # "Primary caregiver is her sister, ..., who assists with daily living and medication
            # reminders": a caregiver's role names no condition, and the clause leaves as written
            return t
        if key != "offence":
            labels = _condition_labels(t)
            if label and len(labels) > 1 and label in labels:
                # "moderate intellectual disability and epilepsy": each diagnosis takes its own
                # category, so the second one is never dropped
                label = " and ".join(labels)
            if len(t.split()) > 12 and label:
                # A long clause keeps its sense when the phrases naming the condition can be
                # replaced cleanly; otherwise it becomes the whole-clause statement.
                soft = _soften(
                    t,
                    table,
                    _DISABILITY_PHRASES,
                    _DISABILITY_MODIFIERS,
                    adjectives=_DISABILITY_ADJECTIVES,
                )
                if soft is not None:
                    return soft
            elif len(t.split()) > 12:
                return t
            if re.match(r"(?i)has\b", t):
                return f"has {label}" if label else "has a health condition"
            verb = re.search(
                r"\s+(?:heals?|healed|improves?|improved|recovers?|recovered|resolves?|resolved"
                r"|stabili[sz]es?|settles?)$",
                t,
                re.IGNORECASE,
            )
            if verb and grammar_slot(before) in ("np", "bare"):
                # "once his leg heals": the clause keeps its verb, so what leaves reads "once his
                # health condition heals" and never ends mid-clause
                return _short_diagnosis(t[: verb.start()], label, before) + verb.group(0)
            return _short_diagnosis(t, label, before)
        # A prior warning stays a prior warning; only a current matter is described as current;
        # a denial, a withdrawn charge or a relative's record is never turned into the client's;
        # a negation stays a negation; an order or a recommendation keeps its terms.
        tl = t.lower()
        what = label or "an offence matter"
        if label is None and not re.search(
            r"\b(?:charg\w*|convict\w*|arrest\w*|records?|caution\w*|warn\w*|probation|diversion"
            r"|previous|prior|history|antecedents?|court|police|investigat\w*|allege\w*|accus\w*"
            r"|admit\w*|denie[sd]|deny|involve\w*|caught|trouble|offend\w*|clean|first)\b",
            tl,
        ):
            # "Requesting the school's support ... without disclosing the offence to classmates"
            # names no offence and states nothing about one: it leaves as written, never as a
            # statement about the client's record
            return t
        # A short span that names only the offence ("criminal trespass" after "Second, ") takes
        # the category in place, in the form the words before it need; a statement of its own
        # there ("is the subject of a current matter") would leave a fragment.
        phrase = _offence_phrase(t)
        if phrase and grammar_slot(before) in ("np", "bare", "clause"):
            slot = grammar_slot(before)
            noun = phrase.split(" ", 1)[1]
            if slot == "bare":
                return noun
            return phrase[0].upper() + phrase[1:] if slot == "clause" else phrase
        # A clause that is one of several charges ("and a separate charge of ... , which was
        # withdrawn") keeps its conjunction, its dates and its status: replacing the offence in
        # place does that when it reads cleanly.
        lead = _CHARGE_LEAD.match(t)
        if lead and _STATUS.search(tl):
            soft = _soften(
                t, OFFENCE_CATEGORIES, _OFFENCE_PHRASES, _OFFENCE_MODIFIERS, _OFFENCE_HEADS
            )
            if soft is not None:
                return soft
        # The disposition of a matter (withdrawn, dropped, acquitted, discharged, no further
        # action) is kept with its basis: "charge withdrawn, cleared by CCTV" must not leave as
        # "an allegation the client disputes", which reads as an open matter.
        if _DISPOSITION.search(tl) and not _RELATIVE_RECORD.search(tl):
            out = _disposition_statement(tl, what, t)
            return (lead.group(0) if lead else "") + out
        # A charge that is pending or fixed for hearing stays undecided, with its court and dates.
        if _PENDING.search(tl) and not _RELATIVE_RECORD.search(tl):
            soft = _soften(
                t, OFFENCE_CATEGORIES, _OFFENCE_PHRASES, _OFFENCE_MODIFIERS, _OFFENCE_HEADS
            )
            if soft is not None:
                return soft
            return (lead.group(0) if lead else "") + _pending_statement(t, what)
        if re.search(
            r"\b(?:no|never|without|not|nil)\b[^.;\n]{0,24}\b(?:previous|prior|record|charge|conviction|offen[cs]\w*|offending|involvement|antecedent|trouble with the law|in trouble|police involvement|history)",
            tl,
        ) or re.search(
            r"\bnever been in trouble\b|\bclean record\b|\bfirst (?:contact|offence|time)\b", tl
        ):
            if re.search(r"\bfirst (?:offence|time)\b", tl) and _CURRENT_EVENT.search(tl):
                # "caught shoplifting on 12 Sep, first time": a current matter and no prior record
                dates = re.findall(_DATE, t, re.IGNORECASE)
                on = f" on {dates[0]}" if dates else ""
                return f"is the subject of a current matter: {what}{on}; no prior offence record is noted"
            return "no prior offence record is noted"
        if re.search(
            r"\b(?:denie[sd]|deny|did not know|didn't know|not aware|unaware|no involvement|not involved|maintains? (?:his|her|their) innocence)\b",
            tl,
        ):
            return f"an allegation of {what} is on record; the client disputes it"
        if re.search(r"\bclosed\b", tl):
            return f"a matter of {what} is on record and closed"
        if _RELATIVE_RECORD.search(tl):
            return f"a family member or associate has a record of {what}"
        if len(t.split()) > 8 or re.search(
            r"\b(?:order|months?|curfew|cso|community service|hours|recommend\w*|condition\w*|review|outcome|diversion|guidance programme)\b",
            tl,
        ):
            # Keep the sentence and replace the phrases that name the offence, when that reads
            # cleanly; otherwise fall through to the whole-clause statement.
            soft = _soften(
                t, OFFENCE_CATEGORIES, _OFFENCE_PHRASES, _OFFENCE_MODIFIERS, _OFFENCE_HEADS
            )
            if soft is not None:
                return soft
        # "prior" counts as history only next to a record noun: "low prior risk" is not a record.
        past = re.search(
            r"\b(?:prev\w*|prior|past|earlier|previously)\b[^.;\n]{0,12}\b(?:record|conviction|offen[cs]\w*|charge|warning|caution|antecedent|matter|history)\b"
            r"|\b(?:history of|warning|caution)\b",
            tl,
        )
        if re.search(r"\bwarn(?:ing|ed)\b|\bcaution(?:ed)?\b", tl):
            return f"has a prior police warning on record ({what})"
        if past:
            return f"has a prior record of {what}"
        # the date of the matter stays with it, so that two matters remain two
        dates = re.findall(_DATE, t, re.IGNORECASE)
        return f"is the subject of a current matter: {what}" + (f" on {dates[0]}" if dates else "")
    if rule == "status_only":
        if key == "ppo":
            tl = t.lower()
            if not _ORDER_WORD.search(t):
                if not _HEARING_CUE.search(t):
                    # No order and no hearing named: a span such as "applied for ComCare" is not a
                    # protection-order clause, and the rule must not invent one.
                    return t
                # a hearing clause without the order named: its date and venue never leave
                return "a court hearing is scheduled (date on record)"
            past = re.search(
                r"\b(?:20[0-2]\d|last year|previous\w*|earlier|prior|in the past)\b", tl
            )
            if re.search(
                r"\bno\b[^.;\n]{0,25}\b(?:order|ppo|application)\b[^.;\n]{0,30}\b(?:applied|made|sought|in place|granted|filed)|\bnever applied\b|\bno (?:ppo|order) (?:is |has been )?(?:in place|applied)"
                # "has not filed a PPO", "never filed", "yet to apply": no application exists
                r"|\b(?:(?:has|have|had|did|does|is)\s+not|hasn't|didn't|never|yet to)\s+(?:yet\s+)?"
                r"(?:filed|file|applied|apply|applying|sought|seek|lodged|lodge|taken out|take out)\b",
                tl,
            ):
                return "no protection order application is on record"
            if len(t.split()) > 12 and not re.search(
                r"^\s*(?:a |the )?(?:ppo|protection order)", tl
            ):
                # An assessment or plan that mentions the order keeps its sense; only the order's
                # specifics (type, dates, hearing and venue) are generalised in place.
                return _drop_court_specifics(_generalise_order_terms(t))
            # "No PPO yet", "no protection order in place": a clear negative stays a negative
            # (it must never reach the "in place" test below, nor the neutral fallback).
            if re.search(
                r"\bno\s+(?:ppo|(?:personal\s+)?protection order|expedited order|deo"
                r"|domestic exclusion order)s?\b(?!\s+(?:hearing|mention))",
                tl,
            ) and not re.search(r"\bno longer\b", tl):
                if re.search(r"consider|thinking about|may apply|might apply|plans? to apply", tl):
                    return "no protection order is on record; one is being considered"
                return "no protection order is on record"
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
            if plan_sentence(before, text) or _ARRANGED_ASSESSMENT.search(t):
                # "Refer for formal capacity assessment": an assessment arranged or requested is
                # part of the plan and states no finding
                return t
            head = _ASSESSMENT_HEADER.match(t)
            if head and not _states_capacity(t[head.end() :]):
                # "Capacity assessment for Mdm Noraini, 58": a heading that names the assessment
                # and states no finding
                return t
            if not _states_capacity(t) and not _NO_PROXY.search(t.lower()):
                # A deputy or donee mentioned without a statement about capacity ("with the
                # deputy present") is not a capacity finding; the never_leak rule for deputyship
                # status applies to it instead.
                return t
            parts = _join_elided(_subclauses(t))
            if (
                len(parts) > 1
                and any(not _states_capacity(p) for p, _ in parts)
                and not _other_attribute(parts, _CAPACITY_STATEMENT, "capacity")
            ):
                out = []
                for i, (p, sep) in enumerate(parts):
                    if _states_capacity(p):
                        p = _capacity_statement(p, note)
                        if i == 0 and t[:1].isupper():
                            p = p[0].upper() + p[1:]
                    out.append(p + sep)
                return "".join(out)
            return _capacity_statement(t, note)
        return f"{key.replace('_', ' ')} recorded"
    if rule == "keep_event_drop_specifics":
        parts = _subclauses(t)
        if len(parts) > 1 and not _other_attribute(
            parts, _DV_CUE, "dv_disclosure", handled=("ppo",)
        ):
            # Each sub-clause that describes the violence is generalised on its own, so that a
            # denial next to a disclosure stays a denial and an assessment or a readiness
            # statement without a cue stays as written.
            out: list[str] = []
            last_who: str | None = None
            for i, (p, sep) in enumerate(parts):
                if _DV_CUE.search(p):
                    label, body = _split_label(p)
                    # "her partner slapped her ... and has threatened to ...": a sub-clause with no
                    # subject of its own keeps the person the one before it named
                    elided = re.match(r"\s*(?:has|have|had|is|was|also|then|later)\b", body)
                    p = label + _dv_statement(body, last_who if elided else None)
                    last_who = _dv_who(body.lower(), last_who if elided else None)
                    if i == 0 and not label and t[:1].isupper():
                        p = p[0].upper() + p[1:]
                    if out and out[-1].rstrip(" ,;").lower().endswith(p.lower()):
                        continue  # the same statement twice in a row: keep one
                elif _ORDER_WORD.search(p):
                    # "... and there is no PPO": the protection-order sub-clause keeps its status
                    p = generalise_attribute("ppo", p, "status_only", pack_id)
                out.append(p + sep)
            return "".join(out).rstrip(" ,;")
        label, body = _split_label(t)
        return label + _dv_statement(body)
    if rule == "age_band" and plan_sentence(before, text):
        return t
    if rule == "age_band":
        # The age is the number next to an age cue, never a day of the month or a year.
        m = re.search(
            r"(?:\b(?:aged?|age:?)\s*(\d{1,2})\b|\b(\d{1,2})\s*(?:-|\s)?(?:year[- ]old|yo|y/o|years?\s+old)\b|,\s*(\d{1,2})\s*,"
            r"|\b(?:is|was)\s+(\d{1,2})\s+(?:and|years?)\b)",
            t,
            re.IGNORECASE,
        )
        age = next((g for g in (m.groups() if m else ()) if g), None)
        if age:
            return "is a minor aged " + age_band(int(age), 3)
        if re.search(r"\bcharges?\b|\bhearing\b|\bmention\b", t, re.IGNORECASE) and not re.search(
            r"\ba minor\b|\bminor status\b|\bunder (?:the age of )?\d|\bbelow \d|\bjuvenile\b",
            t,
            re.IGNORECASE,
        ):
            # "The second charge is pending before the Youth Court" states where a charge stands;
            # the court's name is not a statement about age, and the offence rule keeps the clause
            return t
        return "is a minor"
    return t


_RELATIVE_RECORD = re.compile(
    r"\b(?:cousin|brother|sister|father|mother|uncle|aunt|friend|boyfriend|girlfriend|partner|husband|wife|relative|sibling)\b"
    r"(?:[^.;\n]{0,25}\b(?:has|had|was|were|with|holds|got|served|is|been)\b[^.;\n]{0,20}\b(?:convict\w*|criminal record|record|charg\w*|arrest\w*|prison|jail|probation|sentenced)\b"
    r"|(?:'s|\u2019s)\s+(?:\w+\s+)?(?:charges?|records?|cases?|convictions?|arrests?)\b)"
)
_DISPOSITION = re.compile(
    r"\b(?:withdrawn|withdrew|dropped|dismissed|acquitted|acquittal|discharged|discharge"
    r"|discontinued|not proceeded|no further action|nfa)\b"
)
_BY_PROSECUTION = re.compile(r"\bby (?:the )?(?:prosecution|police|agc|attorney-general)")
_CLEARED = re.compile(
    r"\bnot involved\b|\bno involvement\b|\bcleared\b|\binnocent\b|\bwrong person\b"
    r"|\bmistaken identity\b|\bnot (?:the one|responsible)\b"
)
_CLIENT_DENIAL = re.compile(
    r"\b(?:denie[sd]|deny|denying|maintains? (?:his|her|their) innocence)\b"
)


_CHARGE_LEAD = re.compile(
    r"^\s*(?:(?:and|but|while|whereas)\s+|(?:first(?:ly)?|second(?:ly)?|third(?:ly)?|finally)\s*,?\s+)",
    re.IGNORECASE,
)
_STATUS = re.compile(
    r"\b(?:withdrawn|withdrew|dropped|dismissed|acquitted|discharged|admitted|pleaded|convicted"
    r"|pending|fixed for|awaiting|adjourned|stood down)\b"
)
_CURRENT_EVENT = re.compile(
    r"\b(?:caught|arrested|charged|picked up|apprehended|nabbed|detained|kena)\b"
)
_PENDING = re.compile(
    r"\bpending\b|\bfixed for (?:hearing|mention|trial|plea)|\bawaiting (?:trial|hearing|mention"
    r"|sentenc\w*)|\badjourned\b|\byet to be (?:heard|tried|decided)|\bnext mention\b"
)


_CAREGIVER_SUBJECT = re.compile(
    r"^\s*(?:(?:the\s+)?(?:primary|main|secondary)\s+)?(?:caregiver|carer)\b"
    r"|^\s*(?:his|her|their|the client'?s|client'?s)\s+(?:mother|father|sister|brother|son|daughter"
    r"|wife|husband|grandmother|grandfather|aunt|uncle|niece|nephew|caregiver|carer|helper)\b",
    re.IGNORECASE,
)


def _caregiver_sentence(before: str, text: str) -> bool:
    """Whether the sentence holding ``text`` is about a caregiver or a relative, not the client."""
    return bool(_CAREGIVER_SUBJECT.match(_sentence(before, text)))


def _names_condition(t: str) -> bool:
    """Whether a clause names a condition, a diagnosis or a disability; "medication" alone does
    not."""
    from socareguard.detect.attributes import CUES

    rest = re.sub(r"(?i)\bmedications?\b", " ", t)
    return bool(CUES["diagnosis"].search(rest) or CUES["disability"].search(rest))


def _condition_labels(t: str) -> list[str]:
    """The category of each condition a clause names, in order, each once."""
    found: list[tuple[int, str]] = []
    for p, lab in _DISABILITY_PHRASES + _DISABILITY_ADJECTIVES:
        for m in re.finditer(rf"(?<![\w-])(?:{p})(?![\w-])", t, re.IGNORECASE):
            found.append((m.start(), lab))
    out: list[str] = []
    for _, lab in sorted(found):
        if lab not in out:
            out.append(lab)
    return out


def _offence_phrase(t: str) -> str | None:
    """The category of a span that is nothing but a phrase naming an offence."""
    mods = rf"(?:(?:{_OFFENCE_MODIFIERS}|alleged|suspected|attempted)\s+)*"
    for p, lab in _OFFENCE_PHRASES:
        if re.fullmatch(rf"{mods}(?:{p})", t.strip(), re.IGNORECASE):
            return lab
    return None


def _pending_statement(t: str, what: str) -> str:
    """A pending charge as a plain statement: its court and its dates are kept."""
    venue = re.search(rf"\b(?:before|at|in)\s+{_VENUE}\b", t, re.IGNORECASE)
    fixed = re.search(
        rf"\bfixed for (?:hearing|mention|trial|plea)(?:\s+(?:on|at)\s+{_DATE})?", t, re.IGNORECASE
    )
    out = f"a charge of {what} is pending"
    if venue:
        out += " " + venue.group(0)
    if fixed:
        out += ", " + fixed.group(0)
    return out


def _disposition_statement(tl: str, what: str, t: str = "") -> str:
    """The generalised form of an offence clause that records how the matter ended: the ending
    and its basis stay, the offence becomes its category, and the dates stay with the charge
    (the date it was laid before the ending, the date of the ending after it)."""
    what = "an offence" if what == "an offence matter" else what
    by = " by the prosecution" if _BY_PROSECUTION.search(tl) else ""
    end = _DISPOSITION.search(tl)
    laid = ended = ""
    if t and end:
        before = re.findall(_DATE, t[: end.start()], re.IGNORECASE)
        after = re.findall(_DATE, t[end.start() :], re.IGNORECASE)
        laid = f" on {before[-1]}" if before else ""
        ended = f" on {after[0]}" if after else ""
    what = what + laid
    if re.search(r"\bdischarge(?:d)? not amounting to an? acquittal\b|\bdnaa\b", tl):
        out = (
            f"the client was given a discharge not amounting to an acquittal on a charge of {what}"
        )
    elif re.search(r"\bdischarge amounting to an? acquittal\b|\bdaa\b", tl):
        out = f"the client was given a discharge amounting to an acquittal on a charge of {what}"
    elif re.search(r"\bacquitt(?:ed|al)\b", tl):
        out = f"the client was acquitted of a charge of {what}"
    elif re.search(r"\bconditional(?:ly)? discharge", tl):
        out = f"the client was given a conditional discharge for {what}"
    elif re.search(r"\bwithdr(?:awn|ew)\b|\bdiscontinued\b|\bnot proceeded\b", tl):
        out = f"a charge of {what} was withdrawn{by}{ended}"
    elif re.search(r"\bdropped\b", tl):
        out = f"a charge of {what} was dropped{by}{ended}"
    elif re.search(r"\bdismissed\b", tl):
        out = f"a charge of {what} was dismissed{ended}"
    elif re.search(r"\bdischarged?\b", tl):
        out = f"the client was discharged on a charge of {what}"
    else:  # no further action
        out = f"a matter of {what} was closed with no further action"
    if re.search(r"\binsufficient evidence\b|\black of evidence\b", tl):
        out += " for lack of evidence"
    if _CLEARED.search(tl):
        out += "; the evidence showed the client was not involved"
    elif _CLIENT_DENIAL.search(tl):
        out += "; the client denies involvement"
    return out


_CAPACITY_STATEMENT = re.compile(
    r"\b(?:capacity|able to|unable|understand\w*|weigh\w*|retain\w*|decision[- ]making|lacks?"
    r"|mental capacity act|MCA|assent|supported decision|fluctuat\w*|could not (?:hold|decide))\b",
    re.IGNORECASE,
)
# A deputy's or donee's appointment names the Act or the deputyship; it says nothing about the
# client's own capacity and belongs to the deputyship never_leak rule.
_APPOINTMENT = re.compile(
    r"\b(?:(?:has been|have been|had been|was|is|were)\s+)?(?:appointed|named|registered)\s+"
    r"(?:as\s+)?(?:(?:her|his|their|the|a)\s+)?(?:court[- ]appointed\s+)?(?:deputy|donee|guardian)\b"
    r"|\bcourt[- ]appointed\s+(?:deputy|guardian)\b|\bdeputyship order\b"
    r"|\blasting power of attorney\b|\bLPA\b|\bdonee\b|\b(?:under|by)\s+the\s+court\b"
    r"|\b(?:under\s+)?(?:the\s+)?(?:mental capacity act|MCA)\b",
    re.IGNORECASE,
)


# A named person or a relative appointed as deputy or donee: the clause is about that person.
_PERSON_APPOINTED = re.compile(
    r"\b(?:son|daughter|sister|brother|mother|father|wife|husband|niece|nephew|aunt|uncle|cousin"
    r"|relative|friend|Mdm|Mr|Mrs|Ms|Madam)\b[^.;\n]{0,60}?\b(?:appointed|named|registered|is|was|as"
    r"|holds|has)\b[^.;\n]{0,30}?\b(?:deputy|donee|guardian|lasting power of attorney|LPA)\b",
    re.IGNORECASE,
)


def _states_capacity(t: str) -> bool:
    """Whether a clause states something about the client's capacity. A clause that appoints a
    named person or a relative as deputy or donee does not, unless it says something about
    capacity beyond the appointment and the Act it names: that clause belongs to the deputyship
    never_leak rule, and rewriting it as a capacity finding inverts its subject."""
    if not _CAPACITY_STATEMENT.search(t):
        return False
    if _PERSON_APPOINTED.search(t):
        return bool(_CAPACITY_STATEMENT.search(_APPOINTMENT.sub(" ", t)))
    return True


_ARRANGED_ASSESSMENT = re.compile(
    r"\b(?:refer\w*|request\w*|arrang\w*|schedul\w*|obtain\w*|liais\w*|propos\w*|pending|plan\w*"
    r"|book\w*|await\w*)\b[^.;\n]{0,60}\bcapacity assessment\b",
    re.IGNORECASE,
)


_NO_PROXY = re.compile(
    r"\b(?:not|no|isn't|is not|without|nil)\b[^.]{0,20}\b(?:deputy|deputyship|donee|lpa)"
    r"|\b(?:deputy|deputyship|donee|lpa)\b[^.;\n]{0,12}\b(?:none|nil|not appointed|no)\b"
)
# "No capacity assessment has been done" states that no assessment exists, not that the client
# lacks capacity: the words "no capacity" in it are never a finding.
_NO_ASSESSMENT = re.compile(
    r"\b(?:no|nil|without an?)\s+(?:formal\s+)?(?:mental\s+)?capacity\s+assessments?"
    r"(?:\s+(?:has|have|had|is|was)\s+(?:yet\s+|ever\s+)?(?:been\s+)?(?:done|conducted|carried out"
    r"|completed|performed|made|on record|arranged))?"
    r"|\bcapacity\s+(?:has|had)\s+(?:not|never)\s+(?:yet\s+)?been\s+(?:formally\s+)?assessed"
    r"|\bnot\s+(?:yet\s+)?(?:been\s+)?(?:formally\s+)?assessed\s+for\s+(?:mental\s+)?capacity",
    re.IGNORECASE,
)
_ASSESSMENT_HEADER = re.compile(
    r"^\s*(?:mental\s+)?capacity\s+assessment\s*(?:for|of|re:?|on)\b", re.IGNORECASE
)
_LACK = r"\black|\bnot have\b|\bno capacity\b(?!\s+assess)|\bunable to (?:make|decide|consent)\b"
_NEGATIVE = re.compile(
    rf"{_LACK}|unable|impair|fluctuat|limited|in question|doubt|unclear"
    r"|\b(?:not|n't|could not|cannot|unable to)\s+(?:\w+\s+){0,2}?(?:understand|retain|weigh|hold"
    r"|use|communicat)"
)
_POSITIVE = re.compile(
    r"has capacity|have capacity|demonstrat|able to|confirmed|retains capacity|capacity to make"
    r"|presumed|intact|\bunderstood\b|\bheld (?:them|it|the information)\b|\bgave reasons\b"
    r"|\bweighed\b|\bretained\b|\bcommunicated (?:a|her|his|their) (?:choice|decision)\b"
)
# The decision a capacity finding concerns. Capacity is decision-specific, so a finding keeps the
# kind of decision it is about ("has capacity for day-to-day decisions"); the kinds are generic and
# identify no one.
_DECISIONS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"financ|money|propert|\bbank|\bcpf\b|asset|budget|payments?\b|\bbills?\b",
            re.IGNORECASE,
        ),
        "financial and property decisions",
    ),
    (
        re.compile(r"medical|treatment|surgery|medication|health ?care|operation\b", re.IGNORECASE),
        "healthcare decisions",
    ),
    (
        re.compile(
            r"where (?:to|she|he|they) (?:should )?(?:live|lives|stay)|residen|accommodation"
            r"|living arrangement|nursing home|care home|move (?:to|into)",
            re.IGNORECASE,
        ),
        "decisions about where to live",
    ),
    (
        re.compile(
            r"day-to-day|daily (?:activit|living|routine|life|care)|personal care|free time"
            r"|leisure|everyday",
            re.IGNORECASE,
        ),
        "day-to-day decisions",
    ),
    (re.compile(r"employ|\bwork\b|\bjob\b|\btraining\b", re.IGNORECASE), "employment decisions"),
]
# A relative or caregiver who signs or consents on the client's behalf.
_PROXY_CONSENT = re.compile(
    r"\b(?:signed|signs|consented|consents|gave (?:her |his |their )?consent|agreed|agrees)\b"
    r"[^.;\n]{0,80}?\bon (?:his|her|their|the client'?s|[A-Z][\w-]*'s) behalf\b"
    r"|\bon (?:his|her|their|the client'?s) behalf\b[^.;\n]{0,40}?\b(?:signed|consented)\b",
    re.IGNORECASE,
)


def _decisions(tl: str) -> str | None:
    # the client's own quoted words ("'I want money'") name no decision
    tl = _QUOTED.sub(" ", tl)
    found = [lab for pat, lab in _DECISIONS if pat.search(tl)]
    return " and ".join(found) if found else None


def _lacks_elsewhere(note: str) -> bool:
    """Whether any sentence of the note states a capacity finding against the client."""
    for sent in re.split(r"(?<=[.!?;])\s+|\n", note):
        sl = _NO_ASSESSMENT.sub(" ", sent.lower())
        if "capacity" in sl and _NEGATIVE.search(sl) and not _NO_PROXY.search(sl):
            return True
    return False


def _join_elided(parts: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """A sub-clause with no subject of its own ("held them across the session and gave reasons")
    continues the one before it, so it is never left behind as a fragment when that one is
    restated."""
    out: list[tuple[str, str]] = []
    for p, sep in parts:
        if out and re.match(
            r"\s*(?:and\s+)?(?:held|gave|understood|weighed|retained|communicated|expressed|stated"
            r"|explained|showed|chose|made|was|were|could|can|did|does)\b",
            p,
        ):
            prev, prev_sep = out.pop()
            out.append((prev + prev_sep + p, sep))
        else:
            out.append((p, sep))
    return out


def _capacity_statement(t: str, note: str = "") -> str:
    tl = t.lower()
    no_assessment = _NO_ASSESSMENT.search(tl)
    body = _NO_ASSESSMENT.sub(" ", tl)
    # A deputy or donee is only evidence against capacity when one is actually in place.
    # "Mother is not her deputy" and "no deputyship order" say the opposite.
    no_proxy = _NO_PROXY.search(body)
    has_proxy = (not no_proxy) and re.search(r"\bdeputy|deputyship|donee|lpa\b", body)
    negative = _NEGATIVE.search(body) or has_proxy
    positive = _POSITIVE.search(body)
    decision = _decisions(body)
    lead = "no capacity assessment has been done; " if no_assessment else ""
    if no_proxy and not negative:
        out = "no deputy or donee is appointed" + (f" for {decision}" if decision else "")
        if not _lacks_elsewhere(note):
            out += "; capacity is presumed"
        if _PROXY_CONSENT.search(note):
            # the fact the model and the judge need: nobody holds authority to consent for the
            # client, and someone consented anyway
            out += "; consent was given by a caregiver without legal authority recorded"
        return lead + out
    if negative and not positive:
        if decision and re.search(_LACK, body):
            return lead + f"lacks capacity for {decision}"
        return lead + f"capacity for {decision or 'this decision'} is in question"
    if positive and not negative:
        return lead + f"has capacity for {decision or 'this decision'}"
    if no_assessment:
        return "no capacity assessment has been done"
    return "capacity for this decision: see record"


# Words that describe family violence inside a sub-clause. A sub-clause without one is not part
# of the disclosure and keeps its wording.
_DV_CUE = re.compile(
    r"\b(?:hit|hits|hitting|push\w*|slap\w*|punch\w*|kick\w*|shout\w*|scold\w*|threw|throw\w*"
    r"|hurt|assault\w*|abus\w*|violen\w*|threat\w*|strangl\w*|chok\w*|monitor\w*|controll\w*"
    r"|coerci\w*|restrict\w*|bruis\w*|injur\w*|beat\w*|harm\w*)\b",
    re.IGNORECASE,
)
_THIRD_PARTY = re.compile(
    r"\b(?:neighbou?rs?|teachers?|school|relatives?|police|friends?|colleagues?|anonymous"
    r"|caller|member of the public|in-laws?|mother-in-law|landlord|security guard|passer-by"
    r"|another agency|hospital|doctor|nurse|the children|her (?:son|daughter|mother|father|sister|brother)"
    r"|his (?:son|daughter|mother|father|sister|brother))\b[^.;\n]{0,30}"
    r"\b(?:report\w*|said|stated|alleg\w*|called|heard|informed|told|raised|flagged|noticed|saw)\b",
    re.IGNORECASE,
)
_CLIENT_SUBJECT = re.compile(
    r"^\s*(?:she|he|the client|client|mdm|mr|ms|mrs)\b[^.;\n]{0,20}\b(?:disclos\w*|said|told|report\w*|stated|shared)",
    re.IGNORECASE,
)
_DENIAL = re.compile(
    r"\b(?:denied|denies|deny|denying)\b|\bnever (?:hit|hurt|touched|beat|harmed|laid a hand)"
    r"|\b(?:has|have|had) not been (?:hit|hurt|harmed|beaten|assaulted|physically)"
    r"|\bnot been (?:hit|hurt|harmed|beaten)|\bdid not (?:hit|hurt|harm|beat)\b",
    re.IGNORECASE,
)
_NEGATED = re.compile(
    r"(?:\b(?:no|nil|without|none)\b(?!\s+(?:longer|choice|one|way|option|matter)\b)"
    r"|\bnot\s+(?:disclosed|reported|observed|experienced|seen)\b)"
    r"(?:\s+[\w-]+){0,3}?\s+(?P<what>physical|violen\w*|abus\w*"
    r"|assault\w*|hit\w*|harm\w*|threat\w*|injur\w*|bruis\w*|marks?)\b",
    re.IGNORECASE,
)
_ASSESSMENT = re.compile(
    r"\b(?:indicators?|signs?|concerns?|suspect\w*|possible|possibly)\b",
    re.IGNORECASE,
)
_DISCLOSURE_VERB = re.compile(
    r"\b(?:disclos\w*|said|told|report\w*|stated|alleg\w*|shared|describ\w*|admitted)\b",
    re.IGNORECASE,
)


_QUOTED = re.compile(
    r"\([^()]*\)|\"[^\"]*\"|\u201c[^\u201d]*\u201d|\u2018[^\u2019]*\u2019"
    r"|(?<![\w'])'(?=\w)[^'\n]*?(?<=[\w.!?)])'(?!\w)"
)


def _subclauses(text: str) -> list[tuple[str, str]]:
    """Split a clause at commas and at "and" before a new predicate: [(part, separator)]. A comma
    inside parentheses or a quotation ("gave reasons ('I like coffee, I want money')") is not a
    clause boundary."""
    masked = _QUOTED.sub(lambda m: "\x01" * len(m.group(0)), text)
    pieces, pos = [], 0
    for m in re.finditer(
        r"(,\s+|\s+(?:and|but)\s+(?=(?:has|have|had|is|was|does|did|says|said|will|would|wants|"
        r"is not|has not|not|there (?:is|are|was|were|has been))\b))",
        masked,
    ):
        pieces += [text[pos : m.start()], text[m.start() : m.end()]]
        pos = m.end()
    pieces.append(text[pos:])
    out: list[tuple[str, str]] = []
    for i in range(0, len(pieces), 2):
        sep = pieces[i + 1] if i + 1 < len(pieces) else ""
        part = pieces[i]
        # A fragment of one or two words ("Razak" in "her husband, Razak, hit her") is not a
        # clause of its own, so it stays with the text before it.
        if out and (len(part.split()) < 3 or len(out[-1][0].split()) < 3):
            prev, prev_sep = out.pop()
            out.append((prev + prev_sep + part, sep))
        else:
            out.append((part, sep))
    return out


def _other_attribute(
    parts: list[tuple[str, str]],
    cue: re.Pattern[str],
    key: str,
    handled: tuple[str, ...] = (),
) -> bool:
    """Whether a sub-clause that would be kept as written names another sensitive attribute (a
    diagnosis, a safety plan, a protection order). The clause then stays one statement, as the
    other attribute's own rule never sees it; an attribute in ``handled`` is generalised by the
    caller in its own sub-clause."""
    from socareguard.detect.attributes import CUES

    return any(
        pat.search(p)
        for p, _ in parts
        if not cue.search(p)
        for k, pat in CUES.items()
        if k != key and k not in handled
    )


def _split_label(text: str) -> tuple[str, str]:
    """'Assessment: emotional abuse ...' -> ('Assessment: ', 'emotional abuse ...')."""
    m = re.match(r"^\s*([A-Z][A-Za-z ]{0,24}:\s*)", text)
    return (m.group(1), text[m.end() :]) if m else ("", text)


def _dv_who(tl: str, default: str | None = None) -> str:
    return (
        "her husband"
        if "husband" in tl
        else "his wife"
        if "wife" in tl
        else "her partner"
        if "partner" in tl
        else "an adult son"
        if re.search(r"\bson\b", tl)
        else default or "a family member"
    )


def _dv_statement(text: str, subject: str | None = None) -> str:
    """The generalised form of one sub-clause that mentions family violence. A denial or a
    negation stays negative, a third party's report is not the client's disclosure, and an
    assessment is not a disclosure either. ``subject`` is the person an earlier sub-clause named,
    for a sub-clause that names nobody."""
    tl = text.lower()
    who = subject or _dv_who(tl)
    physical = re.search(
        r"hit|push|slap|punch|kick|strangl|chok|hurt|injur|bruis|assault|threw|beat|physical", tl
    )
    control = re.search(r"monitor|control|coerci|isolat|money|phone|threat|financ|restrict", tl)
    emotional = re.search(r"emotional|verbal|scold|shout|insult|belittl|humiliat|yell", tl)
    if _DENIAL.search(tl):
        return f"denied physical violence by {who}" + (
            "; described controlling behaviour" if control else ""
        )
    neg = _NEGATED.search(tl)
    if neg:
        what = neg.group("what")
        if re.match(r"injur|bruis|mark", what):
            return "no visible injury noted"
        if re.match(r"threat", what):
            return "no threats disclosed"
        return (
            "no physical violence disclosed"
            if physical or "violen" in what
            else ("no family violence disclosed")
        )
    kind = (
        "physical violence"
        if physical
        else "coercive control"
        if control
        else "emotional or verbal abuse"
        if emotional
        else "family violence"
    )
    if _THIRD_PARTY.search(tl) and not _CLIENT_SUBJECT.search(tl):
        return "a third-party report of possible family violence"
    if not _DISCLOSURE_VERB.search(tl) and _ASSESSMENT.search(tl):
        return f"indicators of {kind} noted"
    return f"disclosed {kind} by {who}"


@dataclass(frozen=True)
class GeneralisationRule:
    rule_id: str
    category: str
    original: str
    generalised: str
