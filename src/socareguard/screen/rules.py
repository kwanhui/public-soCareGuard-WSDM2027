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


def audience_is_external(instruction: str, pack_id: str | None = None) -> bool:
    """Whether the practitioner's instruction names a recipient outside the case team. Disclosure
    categories (I10, I14) apply only then; a summary for the worker's own file or supervisor is
    internal. An internal phrase never cancels a named external recipient: "email the principal
    ahead of the case conference" is external."""
    text = instruction or ""
    if COPY_AUDIENCE.search(STATUTORY_AUDIENCE.sub(" ", text)):
        return True
    if PARENT_AUDIENCE.search(text) and pack_id != "youth-offending":
        return True
    remainder = INTERNAL_AUDIENCE.sub(" ", STATUTORY_AUDIENCE.sub(" ", text))
    if pack_id == "youth-offending":
        remainder = PARENT_AUDIENCE.sub(" ", remainder)
    return bool(EXTERNAL_AUDIENCE.search(remainder))
