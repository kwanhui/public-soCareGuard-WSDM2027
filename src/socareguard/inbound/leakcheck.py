"""Leak check on the model's reply.

Three questions, answered before the practitioner sees anything:
1. Does the raw reply contain any *original* identifier? (It never saw one; if it does, the
   model guessed or the outbound step missed it. Either way it is logged.)
2. After restoration, does the reply contain a direct identifier that is neither an original
   nor a surrogate from this session? (An invented identifier: conduct category I13.)
3. Is any surrogate, or a distinctive fragment of one, left unrestored, or was a reformatted
   surrogate left whole because only part of it could be restored?
``passed`` covers 1 and 3; 2 is reported as an I13 flag so that a model hallucination is never
displayed as a privacy failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from socareguard.detect.pipeline import DIRECT, detect
from socareguard.inbound.restore import Restored
from socareguard.outbound.vault import Vault
from socareguard.scenarios.events import DetectedSpan, LeakCheck


@dataclass
class LeakResult:
    passed: bool
    original_echoed: list[str] = field(default_factory=list)
    invented: list[DetectedSpan] = field(default_factory=list)
    unrestored: list[str] = field(default_factory=list)
    partial: list[str] = field(default_factory=list)
    ambiguous_people: list[str] = field(default_factory=list)

    def event(self, seq: int) -> LeakCheck:
        leaks = list(self.invented) + [
            DetectedSpan(start=0, end=0, text=t, type="DIRECT", category="ECHO", detector="vault")
            for t in self.original_echoed
        ]
        return LeakCheck(
            seq=seq,
            passed=self.passed,
            leaks=leaks,
            n_echoed=len(self.original_echoed),
            n_invented=len(self.invented),
            n_unrestored=len(self.unrestored),
            unrestored=list(self.unrestored),
            partial=list(self.partial),
            ambiguous_people=list(self.ambiguous_people),
        )


_MONTHS = {
    "january": "jan", "february": "feb", "march": "mar", "april": "apr", "june": "jun",
    "july": "jul", "august": "aug", "september": "sep", "sept": "sep", "october": "oct",
    "november": "nov", "december": "dec",
}  # fmt: skip
_PLACES = {"ESTATE", "SCHOOL", "FACILITY"}


_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10", "secondary": "sec", "primary": "pri", "block": "blk",
    "road": "rd", "avenue": "ave", "street": "st", "family service centre": "fsc",
    "day activity centre": "dac", "institute of mental health": "imh",
}  # fmt: skip


def _norm(t: str) -> str:
    """Lower-case, month names and number words shortened, punctuation and spacing collapsed:
    '24 August' and '24 Aug', 'Secondary three' and 'Sec 3', '9925 3982' and '99253982' compare
    equal."""
    t = t.lower()
    for long, short in list(_MONTHS.items()) + list(_WORDS.items()):
        t = re.sub(r"\b" + long + r"\b", short, t)
    return re.sub(r"[^a-z0-9]+", "", t)


def _placeholder(text: str, start: int, end: int) -> bool:
    """Whether a detected span sits inside a template slot the model wrote, such as "[School
    Name]" or "[Name of Crisis Shelter]": a slot with no digits names no one. A bracketed
    identifier with digits ("[S1234567D]") is still checked."""
    left = text.rfind("[", 0, start + 1)
    right = text.find("]", end - 1)
    if left == -1 or right == -1 or "]" in text[left:start] or "[" in text[end:right]:
        return False
    slot = text[left + 1 : right]
    return len(slot) <= 60 and "\n" not in slot and not re.search(r"\d", slot)


def leak_check(
    raw_reply: str,
    restored: Restored,
    vault: Vault,
    session: str,
    known_texts: set[str],
    use_presidio: bool = True,
    use_gliner: bool = True,
    source_text: str = "",
    outbound_text: str = "",
) -> LeakResult:
    maps = vault.mappings(session)
    originals = {m.original for m in maps if m.kind == "surrogate"}
    echoed = sorted(o for o in originals if len(o) > 3 and o in raw_reply)
    det = detect(restored.text, use_presidio=use_presidio, use_gliner=use_gliner, attributes=False)
    known = (
        {k.lower() for k in known_texts}
        | {m.original.lower() for m in maps}
        | {m.surrogate.lower() for m in maps}
    )
    # Anything in the note or in what the guard itself sent (surrogates, generalised phrases such
    # as "the east") cannot have been invented by the model.
    source_norm = _norm(source_text + "\n" + outbound_text)
    invented = []
    for h in det.entities:
        norm = _norm(h.text)
        if _placeholder(restored.text, h.start, h.end):
            continue
        if h.category == "URL" and not re.search(r"(?i)^(?:https?://)?[^/]+/[^/\s]", h.text):
            continue  # a home page ("www.msf.gov.sg") names no one
        if (
            (h.category in DIRECT or h.category in _PLACES)
            and h.category != "NAME"
            and h.text.lower() not in known
            and not any(h.text.lower() in k or k in h.text.lower() for k in known)
            and not (source_norm and len(norm) >= 3 and norm in source_norm)
        ):
            invented.append(
                DetectedSpan(
                    start=h.start,
                    end=h.end,
                    text=h.text,
                    type="DIRECT",
                    category=h.category,
                    detector=h.detector,
                    score=h.score,
                )
            )
    # ``passed`` is the privacy claim: nothing original came back and every surrogate was
    # restored. An identifier the model invented is a conduct finding (I13), not a leak.
    # a surrogate that stands for two people stays in the draft, so it counts as unrestored
    unrestored = sorted(set(restored.unrestored_surrogates) | set(restored.ambiguous_surrogates))
    passed = not echoed and not unrestored and not restored.partial
    return LeakResult(
        passed=passed,
        original_echoed=echoed,
        invented=invented,
        unrestored=unrestored,
        partial=list(restored.partial),
        ambiguous_people=list(restored.ambiguous_people),
    )
