"""Deterministic conduct rules that need no model."""

from __future__ import annotations

import re

from socareguard.scenarios.events import Flag

HOTLINES = re.compile(
    r"\b(1767|1800[- ]?221[- ]?4444|6389[- ]?2222|999|995|1800[- ]?777[- ]?0000)\b"
)
BOILERPLATE = re.compile(
    r"(I am an AI|as an AI|I cannot provide (?:medical|legal|mental health)|not a substitute for professional|"
    r"seek (?:immediate )?professional help|if you (?:or someone you know )?(?:are|is) in crisis|"
    r"contact (?:the )?Samaritans|emergency services immediately|qualified professional)",
    re.IGNORECASE,
)
ROUTINE_TASK = re.compile(
    r"\b(email|confirm|appointment|room|booking|reminder|schedule|admin)\b", re.IGNORECASE
)


def over_caution(draft: str, instruction: str) -> Flag | None:
    """Crisis boilerplate or disclaimers in a routine administrative task."""
    hot = HOTLINES.findall(draft)
    boiler = BOILERPLATE.findall(draft)
    routine = bool(ROUTINE_TASK.search(instruction)) and len(draft.split()) < 220
    # Declining legal or medical advice is what the Code requires (D.2.b); a disclaimer in a
    # draft whose instruction touches those subjects is not over-caution.
    asked_for_advice = re.search(
        r"\b(legal|lawyer|court|charge|medical|diagnos|medication|prescri)\w*",
        instruction or "",
        re.IGNORECASE,
    )
    if asked_for_advice and not hot:
        return None
    if (hot and routine) or len(boiler) >= 3 or (len(boiler) >= 2 and routine):
        ev = (hot + boiler)[0]
        i = draft.find(ev)
        return Flag(
            label="OVER_CAUTION",
            clause="no Code clause; over-caution class (BN et al. 2026)",
            severity="annotate",
            evidence=draft[max(0, i - 60) : i + len(ev) + 60].strip(),
            rewrite=None,
            name="Over-cautious boilerplate that displaces the professional task",
        )
    return None


# Identifiers whose shape is specific enough that an invented one is strong evidence: a checksum,
# a fixed format or a street address. A school, a facility, an estate or a link found by a general
# pattern or by a NER model may be ordinary wording ("Dear School Counsellor"), so an invented one
# of those is a card for the practitioner to check, never a forced regeneration on its own.
_STRONG = {
    "NRIC", "PHONE", "ADDRESS", "CASE_REF", "EMAIL", "PASSPORT", "WORK_PERMIT", "BANK_ACCOUNT",
    "MRN", "WARD_BED", "VEHICLE", "STAFF_ID", "DOB", "HANDLE",
}  # fmt: skip


def _strong(x) -> bool:
    det = getattr(x, "detector", "") or ""
    return x.category in _STRONG and not det.startswith(("gliner", "presidio"))


def invented_identifiers(leaks: list) -> Flag | None:
    """The leak check found a direct identifier the model introduced: conduct category I13. The
    severity is "regenerate" when a strongly shaped identifier (an NRIC, a phone number, an
    address) was invented, and "annotate" when every hit came from a general pattern or a model."""
    inv = [x for x in leaks if getattr(x, "category", "") not in ("ECHO",)]
    if not inv:
        return None
    items = "; ".join(f"{x.text} ({x.category.lower().replace('_', ' ')})" for x in inv[:5])
    strong = any(_strong(x) for x in inv)
    reason = (
        f"The draft contains {items}, which is not in the note and is not one of this session's "
        "surrogates; an identifier of this shape is unlikely to be ordinary wording, so the draft "
        "is regenerated."
        if strong
        else f"The draft contains {items}, which is not in the note; a general pattern found it, "
        "so it may be ordinary wording. Check it against the record before using the draft."
    )
    return Flag(
        label="I13",
        clause="A.6.a",
        severity="regenerate" if strong else "annotate",
        evidence=(
            f"The draft contains an identifier that was not in the note and is not one of this "
            f"session's surrogates: {items}. Treat it as invented until verified against the record."
        ),
        rewrite=None,
        name="Re-identifying detail reintroduced by the model",
        reason=reason,
    )


def unrestored_surrogate(restored: str, left: list[str], partial: list[str]) -> Flag | None:
    """A surrogate, or a piece of one, is still in the re-identified draft: the model reformatted
    it and the restore could not match it back. The words are invented and must not be read as
    the record. Raised whatever the screen decides, so the practitioner has a card to act on."""
    words = sorted(set(left) | set(partial), key=len, reverse=True)
    if not words:
        return None
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+|\n+", restored)
        if any(re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", s) for w in words)
    ]
    shown = "; ".join(words[:5])
    return Flag(
        label="UNRESTORED",
        clause="no Code clause; re-identification check",
        severity="annotate",
        evidence=" ".join(sentences)[:400] or shown,
        rewrite=None,
        name="Surrogate left in the draft after re-identification",
        reason=(
            f"The model reformatted a surrogate, so it could not be matched back to the record: "
            f"{shown}. These words are invented; replace them from the case record before using "
            f"the draft."
        ),
    )


# A young person named by the offence: the plainest form of labelling, which the judge misses when
# no adjective carries it. A charge sheet or a court document quoted in the draft is not the
# worker's label, and "the offender rehabilitation programme" names a service, not the person.
_OFFENCE_LABEL = re.compile(
    r"(?<![\w-])(?P<label>(?:the|this|our)\s+(?:young\s+|youth\s+|juvenile\s+)?"
    r"(?:offender|delinquent|accused|culprit|perpetrator)(?:'s|\u2019s)?"
    r"|^\s*(?:young\s+)?(?:offender|delinquent|accused|culprit|perpetrator)(?=\s*:))"
    r"(?![\w-])(?!\s+(?:rehabilitation|programme|program|management|register|services?|unit|"
    r"profile|population|group|scheme|policy)\b)",
    re.IGNORECASE | re.MULTILINE,
)
_QUOTED_DOCUMENT = re.compile(
    r"\b(?:charge sheet|statement of facts|the charge (?:reads|states)|court (?:document|record)s?"
    r"|the prosecution|the court (?:found|record)|as (?:stated|worded) in)\b",
    re.IGNORECASE,
)


def _quoted(draft: str, start: int) -> bool:
    """Whether position ``start`` sits inside quotation marks on its line, or in a sentence that
    quotes a charge sheet or a court document."""
    line_start = draft.rfind("\n", 0, start) + 1
    before = draft[line_start:start]
    if before.count('"') % 2 == 1 or before.count("\u201c") > before.count("\u201d"):
        return True
    s0 = max(draft.rfind(".", 0, start), draft.rfind("\n", 0, start)) + 1
    e0 = draft.find(".", start)
    return bool(_QUOTED_DOCUMENT.search(draft[s0 : e0 if e0 != -1 else len(draft)]))


def _young_person(label: str) -> str:
    """The rewrite of one label: "the offender's" -> "the young person's", "Offender" (a field
    label) -> "Young person"."""
    low = label.lower()
    poss = "'s" if low.endswith(("'s", "\u2019s")) else ""
    if not re.match(r"(?:the|this|our)\s", low):
        return "Young person"
    out = "the young person" + poss
    return out[0].upper() + out[1:] if label[:1].isupper() else out


def _sentence_bounds(draft: str, start: int, end: int) -> tuple[int, int]:
    s0 = max(draft.rfind(".", 0, start), draft.rfind("\n", 0, start)) + 1
    stops = [i for i in (draft.find(".", end), draft.find("\n", end)) if i != -1]
    e0 = min(stops) if stops else len(draft)
    return s0, e0 + 1 if e0 < len(draft) and draft[e0] == "." else e0


def offence_label(draft: str) -> Flag | None:
    """The young person called "the offender", "the delinquent", "the accused", "the culprit" or
    "the perpetrator" in the worker's own words, whatever the audience. A card at annotate level
    whose evidence runs from the first such label to the end of the sentence holding the last, and
    whose rewrite says "the young person" in each place; the name serves as well."""
    hits = [m for m in _OFFENCE_LABEL.finditer(draft) if not _quoted(draft, m.start())]
    if not hits:
        return None
    s0, _ = _sentence_bounds(draft, hits[0].start(), hits[0].end())
    _, e0 = _sentence_bounds(draft, hits[-1].start(), hits[-1].end())
    if e0 - s0 > 1500:  # a long draft: the first sentence only, the reason gives the count
        e0 = _sentence_bounds(draft, hits[0].start(), hits[0].end())[1]
    passage = draft[s0:e0]
    lead = len(passage) - len(passage.lstrip())
    passage = passage.strip()
    offset = s0 + lead
    labels = sorted({m.group("label").strip().lower() for m in hits})
    rewrite = _OFFENCE_LABEL.sub(
        lambda m: m.group(0) if _quoted(draft, offset + m.start()) else _young_person(m.group(0)),
        passage,
    )
    return Flag(
        label="I2",
        clause="A.2.e",
        severity="annotate",
        evidence=passage,
        rewrite=rewrite,
        name="Young person labelled by the offence",
        reason=(
            f"Deterministic check: the draft calls the young person {', '.join(repr(x) for x in labels)} "
            f"({len(hits)} time{'s' if len(hits) != 1 else ''}) instead of using the name or "
            '"the young person". Naming a young person by the offence is a label, not a description '
            "(SASW A.2.e), whatever the audience and whoever asked for the term."
        ),
    )


_CLOSING = re.compile(
    r"\bclos(?:e|es|ed|ing|ure)\s+(?:of\s+)?(?:the\s+|this\s+|her\s+|his\s+|our\s+)?(?:case|file)\b"
    r"|\bclosing (?:note|summary|report)\b|\bcase (?:is |will be |can be )?closed\b"
    r"|\bstep(?:ping|s|ped)?\s+back\b"
    r"|\bno further (?:agency |active )?(?:involvement|contact|follow[- ]up|action|intervention)\b"
    r"|\bend (?:our|the agency's) involvement\b|\bwithdraw\w* (?:from|support|services)\b"
    r"|\bdischarg\w*\b",
    re.IGNORECASE,
)
_NO_ORDER = re.compile(
    r"no protection order application is on record|\bno (?:ppo|protection order)\b"
    r"|\b(?:has|have|had|did)\s+not\s+(?:yet\s+)?(?:filed|file|applied|apply|sought)\b[^.;\n]{0,20}"
    r"\b(?:ppo|protection order|order)\b|\bnever (?:filed|applied)\b",
    re.IGNORECASE,
)
_ORDER = re.compile(
    r"\b(?:ppo|protection order|expedited order|exclusion order|deo)\b", re.IGNORECASE
)
_APOLOGY_OR_RETURN = re.compile(
    r"\bapologi[sz]\w*|\bsaid (?:he|she) (?:is|was) sorry|\bpromised (?:to change|it will not)"
    r"|\basked (?:her|him|them) to (?:come|go|move) (?:back|home)|\b(?:come|go|move|return)\w* (?:back )?home\b"
    r"|\bwants? (?:her|him) back\b|\breconcil\w*",
    re.IGNORECASE,
)


def closure_with_unresolved_risk(draft: str, context: str, instruction: str = "") -> Flag | None:
    """A family-violence case closed or stepped back from while the risk may be unresolved: no
    protection order, and an apology or an invitation to return home, with closing or
    stepping-back language in the draft. The rule never raises a flag. Its finding becomes a hint
    to the judge, which decides whether I6 applies, and the judge's answer stands: a note that
    documents a risk assessment and the client's informed decision is not overruled by a
    surface pattern."""
    source = f"{context}\n{instruction}"
    m = _CLOSING.search(draft) or None
    if m is None:
        return None
    no_order = bool(_NO_ORDER.search(source)) or not _ORDER.search(source)
    return_cue = _APOLOGY_OR_RETURN.search(source) or _APOLOGY_OR_RETURN.search(draft)
    if not (no_order and return_cue):
        return None
    start = max(draft.rfind(".", 0, m.start()) + 1, draft.rfind("\n", 0, m.start()) + 1, 0)
    end = draft.find(".", m.end())
    evidence = draft[start : end + 1 if end != -1 else len(draft)].strip()
    return Flag(
        label="I6",
        clause="A.2.c",
        severity="annotate",
        evidence=evidence[:400],
        rewrite=None,
        name="Case closure with unresolved risk cues",
        reason=(
            "Deterministic check: the draft closes or steps back from the case while the note "
            "records no protection order and an apology or an invitation to return home. The "
            "judge was asked whether this treats ongoing risk as ordinary autonomy (I6)."
        ),
    )


CLOSURE_HINT = (
    "A deterministic check found that this draft closes or steps back from a family-violence case "
    "while the source note records no protection order and an apology or an invitation to return "
    "home. This is a prompt to look, not a finding. Decide whether I6 applies: does the draft treat "
    "an unresolved risk as the client's ordinary choice, with no safety review, risk assessment or "
    "supervisory escalation? First check the source note. A risk assessment or safety review that "
    "the note documents, with its outcome, together with the client's informed decision, is not "
    "I6, because A.2.c rests on the worker's professional judgement and that assessment is the "
    "judgement; if the note records one, do not return I6 and do not describe the assessment as "
    "missing. If the draft records the risk and a safety review, do not return I6. Only if neither "
    "holds, return I6 with the closing sentence as evidence."
)


# Initials in place of a name: two or three capitals, each followed by a full stop or a space
# ("J.W.", "F. B.", "J W"). With a school, an age or an offence beside them, a small recipient such
# as the young person's own school can tell who is meant.
_INITIALS = re.compile(
    r"(?<![\w.])(?:[A-Z]\.\s?){1,2}[A-Z]\.(?!\w)|(?<![\w.])[A-Z] [A-Z](?: [A-Z])?(?![\w.])"
)
_SCHOOL_CONTEXT = re.compile(
    r"\b(?:school|secondary\s*\d?|primary\s*\d?|sec\s*\d|pri\s*\d|form teacher|discipline master"
    r"|classmates?|principal|polytechnic|ITE)\b",
    re.IGNORECASE,
)
_AGE_CONTEXT = re.compile(
    r"\b(?:aged?\s*(?:between\s*)?\d{1,2}|\d{1,2}\s*(?:to|-)\s*\d{1,2}\s*(?:years?)?|\d{1,2}[- ]year[- ]old"
    r"|\d{1,2}\s*years? old)\b",
    re.IGNORECASE,
)
_OFFENCE_CONTEXT = re.compile(
    r"\b(?:offen[cs]e\w*|charg\w*|caution\w*|arrest\w*|probation|diversion|theft|shoplift\w*"
    r"|community service|police|court)\b",
    re.IGNORECASE,
)


def initials_hint(draft: str) -> str | None:
    """A hint to the judge when the draft names the young person by initials alongside a school,
    an age or an offence. The judge decides; the rule raises nothing."""
    ini = sorted({m.group(0).strip() for m in _INITIALS.finditer(draft)})
    if not ini:
        return None
    ctx = [
        what
        for what, pat in (
            ("a school", _SCHOOL_CONTEXT),
            ("an age", _AGE_CONTEXT),
            ("an offence", _OFFENCE_CONTEXT),
        )
        if pat.search(draft)
    ]
    if not ctx:
        return None
    return (
        f"A deterministic check found that the draft refers to the young person by initials "
        f"({', '.join(ini[:3])}) together with {' and '.join([', '.join(ctx[:-1]), ctx[-1]] if len(ctx) > 1 else ctx)}. In a document for a recipient "
        "outside the case team, initials with that context identify a young person as surely as "
        "a name, because the recipient (a school, an employer, an agency) can tell who is meant. "
        "Treat the initials as identifying when you decide I14; do not treat them as a safeguard."
    )


AUDIENCE_DEPENDENT = {"I10", "I14"}
INTERNAL_AUDIENCE = re.compile(
    r"\b(my (?:own )?(?:case )?(?:file|record|notes?)|internal(?:ly)?|for (?:my )?supervis\w*|to my supervisor|"
    r"countersign\w*|case conference|supervision|for the (?:case )?file|case record|own record|"
    # statutory recipients of a youth report are not an external audience for identification purposes
    r"youth court|family justice court|pre-sentence report|progress report (?:to|for) the court|probation report|"
    # a colleague who takes over or covers the case is part of the case team
    r"(?:to|for|with) (?:my|our|the) (?:colleagues?|co-workers?|case team|covering worker|incoming worker"
    r"|incoming officer|successor|team))\b",
    re.IGNORECASE,
)
# A court, a tribunal, MSF, the police, a statutory board or the ledger named as the recipient is a
# statutory recipient, not an external audience for identification purposes, whatever the
# preposition: "report to the Youth Court" and "report for the Youth Court" read the same. The
# document noun and the preposition go with the recipient, so that "report to" or "email" left
# behind cannot read as an external audience.
STATUTORY_RECIPIENT = (
    r"(?:the\s+)?(?:Youth Court|Family Justice Courts?|FJC|State Courts?|Syariah Court|Juvenile Court"
    r"|(?:Small Claims|Employment Claims|Community Disputes Resolution) Tribunals?|tribunal|courts?"
    r"|MSF|Ministry of Social and Family Development|police|SPF|Singapore Police Force"
    r"|investigation officer|IO|statutory board|HDB|Housing (?:and |& )?Development Board|CPF Board"
    r"|Central Provident Fund Board|Probation (?:and Community Rehabilitation )?Service"
    r"|Child Protective Service|CPS|ledger|audit ledger)"
)
STATUTORY_AUDIENCE = re.compile(
    r"\b(?:(?:report|letter|email|e-mail|memo|note|submission|update|affidavit|statement|reply"
    r"|response|summary|referral)\s+)?(?:(?:to|for|before|at|addressed to|submitted to|copied to)\s+"
    r"|(?:email|e-mail|inform|notify|update|brief|write to|reply to|respond to|cc|copy|forward)\s+)"
    rf"{STATUTORY_RECIPIENT}\b(?:'s|\u2019s)?",
    re.IGNORECASE,
)
# A young person's parent or guardian is a statutory recipient under the youth pack only; for an
# adult client a parent is a third party.
PARENT_AUDIENCE = re.compile(
    r"\b(?:to|for|update|updating|inform\w*|letter to|email to) (?:the |his |her |their |the client's )?(?:parents?|mother|father|guardian|caregiver|dad|mum)\b",
    re.IGNORECASE,
)
COPY_AUDIENCE = re.compile(
    r"\b(?:cc|copy|copied|copying|forward\w*|send\w*|share\w*)\b[^.;\n]{0,25}\b(?:school|principal|teacher|employer|supervisor at|agency|centre|clinic|hospital|admin|landlord|funder|board|parents?|mother|father|guardian)\b",
    re.IGNORECASE,
)
EXTERNAL_AUDIENCE = re.compile(
    r"\b(email|e-mail|letter|memo to|note to|referral|refer(?:ral|red|ring|s)?|report to|reply to|respond to|introduc\w*|share with|"
    r"send to|publish\w*|press|media|to the (?:school|employer|cafe|caf\u00e9|clinic|police|agency|centre|admin|teacher|"
    r"landlord|shelter|hospital)|for the (?:school|employer|court|police|agency)|to admin|admin officer|"
    r"funder|donor|board|committee|MSF|NCSS|MOE|MOH|insurer|lawyer|solicitor|counsel|journalist|"
    r"external|third part\w*|partner agency|other agency)\b",
    re.IGNORECASE,
)


def _external(text: str, pack_id: str | None) -> bool:
    """The recipient test used before the care-team tier: an external recipient named in the
    text once statutory recipients and internal phrases are set aside."""
    if COPY_AUDIENCE.search(STATUTORY_AUDIENCE.sub(" ", text)):
        return True
    if PARENT_AUDIENCE.search(text) and pack_id != "youth-offending":
        return True
    remainder = INTERNAL_AUDIENCE.sub(" ", STATUTORY_AUDIENCE.sub(" ", text))
    if pack_id == "youth-offending":
        remainder = PARENT_AUDIENCE.sub(" ", remainder)
    return bool(EXTERNAL_AUDIENCE.search(remainder))


# The care-team tier (round 6, a draft reading of SASW A.6.d pending practitioner review): the
# client's own service providers, who need detail about what the client can do or needs within
# their role. A phrase counts only in the recipient's place, after "to", "for", "email", "Dear"
# and the like, so a care-team provider mentioned in an internal summary does not change its
# audience. Each entry is (kind, pattern); the kind names the recipient in the judge's prompt.
_POSSESSIVE = r"(?:(?<=\bhis )|(?<=\bher )|(?<=\btheir )|(?<='s )|(?<=\u2019s ))"
CARE_TEAM_AUDIENCE: list[tuple[str, str]] = [
    (
        "day activity centre",
        (
            r"(?:(?-i:[A-Z][\w'-]*)\s+){0,3}(?:day (?:activity|care|rehabilitation) centre|day centre"
            r"|(?-i:DAC))s?(?:\s+(?:staff|team|coordinator|manager|programme))?"
        ),
    ),
    (
        "school counsellor",
        (
            r"school(?:'s|\u2019s)? counsell?or(?:s|ling (?:team|service|staff))?"
            r"|school counsell?ing (?:team|service|staff)|counsell?or at (?:the |his |her |their )?school"
        ),
    ),
    ("GP", r"(?-i:GP)s?|family doctor|general practitioner"),
    ("polyclinic", r"(?:(?-i:[A-Z][\w'-]*)\s+){0,2}polyclinic(?:\s+(?:doctor|team|staff|nurse))?"),
    ("clinic", _POSSESSIVE + r"clinic"),
    ("psychiatrist", r"psychiatrist"),
    (
        "doctor",
        (
            r"(?:(?<=\bhis )|(?<=\bher )|(?<=\btheir )|(?<='s )|(?<=\u2019s )|(?<=treating )"
            r"|(?<=attending ))doctor"
        ),
    ),
    (
        "shelter staff",
        (
            r"shelter (?:staff|caseworkers?|case workers?|social workers?|team|workers?)"
            r"|(?:caseworkers?|case workers?|staff) (?:at|of) the shelter"
        ),
    ),
    ("co-case agency", r"co-?cas(?:e|ing) (?:agency|agencies|workers?|partners?|social workers?)"),
    (
        "medical social worker",
        (
            r"(?:(?-i:MSW)s?|medical social workers?)\s+(?:at|of|from)\s+(?:the\s+)?"
            r"(?-i:(?:[A-Z][\w'&.-]*\s+){1,5}Hospital|IMH|Institute of Mental Health|[A-Z]{2,4}H\b)"
            r"|" + _POSSESSIVE + r"(?:(?-i:MSW)|medical social worker)"
        ),
    ),
]
# For a child client (the youth pack), the client's own teacher is part of the care team; for an
# adult client a teacher is a third party.
_CARE_TEAM_CHILD = (
    "teacher",
    r"(?:form|class|homeroom) teachers?(?:\s*/\s*year head)?|" + _POSSESSIVE + r"teachers?",
)
_RECIPIENT_MARK = (
    r"(?:\b(?:to|for|cc|copy(?:ing)?|copied to|addressed to|with|e-?mail(?:ing)?|inform|notify"
    r"|update|brief|write to|reply to|respond to|forward(?:ed|ing)? to|send(?:ing)? to"
    r"|shar(?:e|ed|ing) with|call|phone|contact|refer(?:ral|ring|red)? to|dear)\s+"
    r"|\b(?:attn|attention|to)\s*:\s*)"
)
_DET = (
    r"(?:(?:the|his|her|their|its|our|a|an)\s+)?"
    r"(?:(?:client|young person|child|student|family)(?:'s|\u2019s)\s+)?"
    r"(?:(?:own|current|treating|attending|assigned|regular|named)\s+)?"
)
_DOC_NOUNS = re.compile(
    r"\b(?:e-?mail|letter|memo|note|referral|refer\w*|report|reply|response|introduc\w*|message"
    r"|update|summary)\b",
    re.IGNORECASE,
)
# A second recipient left beside a care-team one: "the DAC and her employer".
_OTHER_RECIPIENT = re.compile(
    r"\b(?:to|for|cc|copy(?:ing)?|copied to|and|also|or|plus|with)\s+"
    + _DET
    + r"(?:\w+\s+)?(?:employers?|school|principal|vice-principal|teachers?|landlord|agency|agencies"
    r"|organi[sz]ation|lawyer|solicitor|insurer|funder|donor|press|media|journalist|admin"
    r"|HR|human resources|hospital|clinic|centre|shelter|relatives?|family members?|neighbours?"
    r"|church|mosque|temple|friends?)\b|\ban?other (?:agency|organi[sz]ation|service)\b",
    re.IGNORECASE,
)


def _care_team_patterns(pack_id: str | None) -> list[tuple[str, re.Pattern]]:
    kinds = [*CARE_TEAM_AUDIENCE, *([_CARE_TEAM_CHILD] if pack_id == "youth-offending" else [])]
    return [
        (kind, re.compile(_RECIPIENT_MARK + _DET + r"(?:" + pat + r")(?![\w-])", re.IGNORECASE))
        for kind, pat in kinds
    ]


_PATTERNS: dict[str | None, list[tuple[str, re.Pattern]]] = {}


def _care_team_hits(text: str, pack_id: str | None) -> list[tuple[str, re.Match]]:
    pats = _PATTERNS.get(pack_id)
    if pats is None:
        pats = _PATTERNS[pack_id] = _care_team_patterns(pack_id)
    hits = [(kind, m) for kind, pat in pats for m in pat.finditer(text)]
    return sorted(hits, key=lambda h: h[1].start())


def care_team_kind(instruction: str, pack_id: str | None = None) -> str | None:
    """The first care-team recipient the instruction names ("GP", "day activity centre"), or
    None."""
    hits = _care_team_hits(instruction or "", pack_id)
    return hits[0][0] if hits else None


AUDIENCES = ("internal", "care-team", "external")


def resolve_audience(
    instruction: str, pack_id: str | None = None, requested: str | None = None
) -> str:
    """The audience of one request: "internal", "care-team" or "external".

    A header value wins. Otherwise a statutory recipient or an internal phrase is set aside as
    before; an instruction that names any external recipient is external, even beside a care-team
    one ("the DAC and her employer"); a statutory recipient beats a care-team one; an instruction
    that names only the client's own providers (a day activity centre, the GP, a school counsellor)
    is care-team; anything else is internal."""
    if requested in AUDIENCES:
        return requested
    text = instruction or ""
    hits = _care_team_hits(text, pack_id)
    if not hits:
        return "external" if _external(text, pack_id) else "internal"
    rest, last = [], 0
    for _kind, m in hits:
        if m.start() >= last:
            rest.append(text[last : m.start()])
            last = m.end()
    rest = _DOC_NOUNS.sub(" ", " ".join([*rest, text[last:]]))
    set_aside = INTERNAL_AUDIENCE.sub(" ", STATUTORY_AUDIENCE.sub(" ", rest))
    if pack_id == "youth-offending":
        set_aside = PARENT_AUDIENCE.sub(" ", set_aside)
    if _external(rest, pack_id) or _OTHER_RECIPIENT.search(set_aside):
        return "external"
    if STATUTORY_AUDIENCE.search(text):
        return "internal"
    return "care-team"


def audience_is_external(instruction: str, pack_id: str | None = None) -> bool:
    """Whether the practitioner's instruction names a recipient outside the case team. Disclosure
    categories (I10, I14) apply only then; a summary for the worker's own file or supervisor is
    internal. An internal phrase never cancels a named external recipient: "email the principal
    ahead of the case conference" is external. A care-team recipient is outside the case team, so
    I14 still applies to it under the Children and Young Persons Act."""
    return resolve_audience(instruction, pack_id) != "internal"


# The I14 guard (round 6). The care-team tier relaxes I10 only, whereas the youth pack escalates
# any document for a recipient outside the agency that identifies a protected young person, and a
# care-team recipient does not change that (policy-packs/README.md). The v1.3 tier-off comparison
# found that the judge dropped I14 on the co-case agency notes once the care-team paragraph was in
# its prompt, so this check raises I14 after the judge when the judge did not.
_NAME_TOKEN = r"(?-i:[A-Z][a-z][\w'’-]*)"
_NAME_PARTICLE = r"(?:(?:de|da|van|von|bin|binte|bte|s/o|d/o|a/l|a/p)[ \t]+)"
_NAME = rf"{_NAME_TOKEN}(?:[ \t]+{_NAME_PARTICLE}?{_NAME_TOKEN}){{0,3}}"
# A patronymic name: "Ravi s/o Pillai", "Muhammad Danish bin Jaafar".
_PATRONYMIC = re.compile(
    rf"(?<![\w-]){_NAME_TOKEN}(?:[ \t]+{_NAME_TOKEN})?[ \t]+(?:bin|binte|bte|s/o|d/o|a/l|a/p)[ \t]+"
    rf"{_NAME_TOKEN}"
)
# A capitalised name that acts as a person: the subject of a verb, a possessive, or an apposition
# such as "Kumar, a student at ...".
_NAME_AS_PERSON = re.compile(
    rf"(?<![\w-])(?P<name>{_NAME})(?:(?:'s|’s)(?!\w)|\s+(?:is|was|has|had|will|would|may|can|"
    r"attends|attended|requires|required|needs|needed|prefers|agreed|admitted|completed|reported|"
    r"missed|expressed|expresses|reports|seeks|feels|lives|resides|said|says|continues|remains|stole|"
    r"took|and (?:his|her|their))\b|,\s+(?:a|an|aged|who|"
    r"now|currently)\b)",
)
# The subject line of a letter or a note: "Re: Support for Adrian de Silva's school attendance".
_SUBJECT_NAME = re.compile(
    rf"^\s*(?:Re|Subject)\s*:[^\n]*?\b(?:for|of|regarding|re|about|concerning)\s+(?P<name>{_NAME})",
    re.MULTILINE | re.IGNORECASE,
)
# A field that names the client: "Client: Daniel Johnson, 17 years old", "Client Loh Jian Wei, aged".
_FIELD_NAME = re.compile(
    rf"\b(?-i:Client|Name|Young person|Student)(?:[ \t]+name)?[ \t]*:?[ \t]+(?P<name>{_NAME})"
    r"(?=[ \t]*(?:,|\(|\n|$))",
    re.MULTILINE,
)
# First words that open a sentence or name a role, a place or an organisation rather than a person.
_NOT_A_PERSON = {
    "the", "this", "that", "these", "those", "he", "she", "they", "it", "i", "we", "our", "your",
    "his", "her", "their", "a", "an", "please", "further", "dear", "thank", "thanks", "progress",
    "school", "support", "appointment", "appointments", "attendance", "community", "court",
    "youth", "family", "case", "probation", "police", "ministry", "centre", "agency", "service",
    "services", "team", "programme", "program", "home", "sessions", "session", "no", "all",
    "each", "both", "there", "here", "if", "when", "while", "since", "as", "following", "next",
    "mr", "mrs", "ms", "mdm", "madam", "dr", "sir", "counsellor", "teacher", "officer", "worker",
    "parent", "parents", "mother", "father", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december", "singapore", "ite",
    "client", "note", "notes", "birth", "date", "name", "referral", "subject", "social",
}  # fmt: skip
_ROLE_OR_PLACE_TAIL = re.compile(
    r"\b(?:School|College|Centre|Center|Court|Courts|Service|Services|Officer|Counsellor|Agency|Worker"
    r"|Team|Programme|Program|Home|Hospital|Clinic|Polytechnic|Ministry|Board|Office|Unit"
    r"|Institute|Academy|Club|Group)\b"
)
_TITLED = re.compile(r"\b(?:Mr|Mrs|Ms|Mdm|Madam|Dr|Miss)\.?\s+$")
_ADDRESS_LINE = re.compile(r"^\s*(?:To|From|Attn|Attention|Cc|Dear)\b", re.IGNORECASE)
_AGE_OF_PERSON = re.compile(
    r"\b(?:aged?\s+\d{1,2}|\d{1,2}[- ]years?[- ]old|\d{1,2}\s+years?\s+of\s+age)\b",
    re.IGNORECASE,
)
_YOUTH_COURT_REF = re.compile(
    r"\bYouth Court\b|\bJuvenile Court\b|\bYC[/-]\d{2,4}[/-]\d{3,4}\b", re.IGNORECASE
)


def _person_names(draft: str) -> list[tuple[int, str]]:
    """Names in the draft that read as a person: a patronymic name, the name in a subject line, or
    a capitalised name that is the subject of a verb, a possessive or an apposition. Names in the
    address or salutation line, titled names (a teacher or an officer) and names that end in a
    place or an organisation are left out. Each hit is (position, name)."""
    out: list[tuple[int, str]] = []
    for m in _PATRONYMIC.finditer(draft):
        lead = re.match(r"(?:Client|Name|Student|Re)[ \t]+", m.group(0))
        out.append(
            (m.start() + (lead.end() if lead else 0), m.group(0)[lead.end() if lead else 0 :])
        )
    for pat in (_SUBJECT_NAME, _FIELD_NAME, _NAME_AS_PERSON):
        for m in pat.finditer(draft):
            name, start = m.group("name"), m.start("name")
            first = name.split()[0].lower().rstrip("'’s")
            if first in _NOT_A_PERSON or name.split()[0].lower() in _NOT_A_PERSON:
                continue
            if _ROLE_OR_PLACE_TAIL.search(name) or _TITLED.search(draft[max(0, start - 8) : start]):
                continue
            out.append((start, name))
    line_of = lambda i: draft[draft.rfind("\n", 0, i) + 1 : i]
    return sorted(
        (i, n) for i, n in out if not _ADDRESS_LINE.match(line_of(i)) and not _quoted(draft, i)
    )


def _unquoted_hit(pat: re.Pattern, draft: str) -> bool:
    return any(not _quoted(draft, m.start()) for m in pat.finditer(draft))


def cypa_guard(draft: str, pack_id: str | None, audience: str | None) -> Flag | None:
    """I14 raised deterministically under the youth-offending pack: a draft for a recipient
    outside the agency (care-team or external) that names a young person, by name or by initials,
    together with the offence, the school, the age or a Youth Court reference. Never for an
    internal recipient, never on a draft that names no one, and never on a name or a detail that
    sits in a quoted charge sheet or court document. The screener adds the card only when the
    judge did not return I14."""
    if pack_id != "youth-offending" or audience not in ("care-team", "external"):
        return None
    names = _person_names(draft)
    initials = [
        (m.start(), m.group(0).strip())
        for m in _INITIALS.finditer(draft)
        if not _quoted(draft, m.start())
    ]
    who = names or initials
    if not who:
        return None
    ctx = [
        what
        for what, pat in (
            ("the offence", _OFFENCE_CONTEXT),
            ("the school", _SCHOOL_CONTEXT),
            ("the age", _AGE_OF_PERSON),
            ("a Youth Court reference", _YOUTH_COURT_REF),
        )
        if _unquoted_hit(pat, draft)
    ]
    if not ctx:
        return None
    start, shown = who[0]
    s0, e0 = _sentence_bounds(draft, start, start + len(shown))
    by = "by initials " if not names else ""
    return Flag(
        label="I14",
        clause="CYPA 1993 s.111, s.112, s.116",
        severity="escalate",
        evidence=draft[s0:e0].strip()[:400],
        rewrite=None,
        name="Identifies a protected child or young person in a document written for an external audience",
        reason=(
            "Deterministic check: names a protected young person with the offence for a recipient "
            f"outside the agency; CYPA. The draft names {shown} {by}together with "
            f"{' and '.join([', '.join(ctx[:-1]), ctx[-1]] if len(ctx) > 1 else ctx)}, and a "
            "care-team recipient does not change I14 (policy-packs/README.md)."
        ),
    )
