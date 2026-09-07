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


def invented_identifiers(leaks: list) -> Flag | None:
    """The leak check found a direct identifier the model introduced: conduct category I13."""
    inv = [x for x in leaks if getattr(x, "category", "") not in ("ECHO",)]
    if not inv:
        return None
    items = "; ".join(f"{x.text} ({x.category.lower().replace('_', ' ')})" for x in inv[:5])
    return Flag(
        label="I13",
        clause="A.6.a",
        severity="regenerate",
        evidence=(
            f"The draft contains an identifier that was not in the note and is not one of this "
            f"session's surrogates: {items}. Treat it as invented until verified against the record."
        ),
        rewrite=None,
        name="Re-identifying detail reintroduced by the model",
    )


AUDIENCE_DEPENDENT = {"I10", "I14"}
INTERNAL_AUDIENCE = re.compile(
    r"\b(my (?:own )?(?:case )?(?:file|record|notes?)|internal(?:ly)?|for (?:my )?supervis\w*|to my supervisor|"
    r"countersign\w*|case conference|supervision|for the (?:case )?file|case record|own record|"
    # statutory recipients of a youth report are not an external audience for identification purposes
    r"youth court|family justice court|pre-sentence report|progress report (?:to|for) the court|probation report)\b",
    re.IGNORECASE,
)
# A young person's parent or guardian is a statutory recipient under the youth pack only; for an
# adult client a parent is a third party.
PARENT_AUDIENCE = re.compile(
    r"\b(?:to|for|update|updating|inform\w*|letter to|email to) (?:the |his |her |their |the client's )?(?:parents?|mother|father|guardian|caregiver|dad|mum)\b",
    re.IGNORECASE,
)
COPY_AUDIENCE = re.compile(
    r"\b(?:cc|copy|copied|copying|forward\w*|send\w*|share\w*)\b[^.;\n]{0,25}\b(?:school|principal|teacher|employer|supervisor at|court|police|agency|centre|clinic|hospital|admin|landlord|funder|board|parents?|mother|father|guardian)\b",
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
    if COPY_AUDIENCE.search(text):
        return True
    if PARENT_AUDIENCE.search(text) and pack_id != "youth-offending":
        return True
    remainder = INTERNAL_AUDIENCE.sub(" ", text)
    if pack_id == "youth-offending":
        remainder = PARENT_AUDIENCE.sub(" ", remainder)
    return bool(EXTERNAL_AUDIENCE.search(remainder))
