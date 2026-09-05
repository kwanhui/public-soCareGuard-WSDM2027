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
    if (hot and routine) or len(boiler) >= 2 or (boiler and routine):
        ev = (hot + boiler)[0]
        i = draft.find(ev)
        return Flag(
            label="OVER_CAUTION",
            clause="none (research grounding: BN et al. 2026)",
            severity="regenerate",
            evidence=draft[max(0, i - 60) : i + len(ev) + 60].strip(),
            rewrite=None,
        )
    return None


def invented_identifiers(leaks: list) -> Flag | None:
    """The leak check found a direct identifier the model introduced: conduct category I13."""
    inv = [x for x in leaks if getattr(x, "category", "") not in ("ECHO",)]
    if not inv:
        return None
    return Flag(
        label="I13",
        clause="A.6.a",
        severity="regenerate",
        evidence="; ".join(f"{x.category}: {x.text}" for x in inv[:5]),
        rewrite=None,
    )


AUDIENCE_DEPENDENT = {"I10", "I14"}
EXTERNAL_AUDIENCE = re.compile(
    r"\b(email|e-mail|letter|memo to|note to|referral|refer\w*|report to|reply to|respond to|introduc\w*|share with|"
    r"send to|publish\w*|press|media|to the (?:school|employer|cafe|caf\u00e9|clinic|court|police|agency|centre|admin|teacher|"
    r"landlord|shelter|hospital)|for the (?:school|employer|court|police|agency)|to admin|admin officer)\b",
    re.IGNORECASE,
)


def audience_is_external(instruction: str) -> bool:
    """Whether the practitioner's instruction names a recipient outside the case team. Disclosure
    categories (I10, I14) apply only then; a summary for the worker's own file or supervisor is internal."""
    return bool(EXTERNAL_AUDIENCE.search(instruction or ""))
