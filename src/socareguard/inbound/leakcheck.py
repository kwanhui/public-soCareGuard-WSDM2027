"""Leak check on the model's reply.

Three questions, answered before the practitioner sees anything:
1. Does the raw reply contain any *original* identifier? (It never saw one; if it does, the
   model guessed or the outbound step missed it. Either way it is logged.)
2. After restoration, does the reply contain a direct identifier that is neither an original
   nor a surrogate from this session? (An invented identifier: conduct category I13.)
3. Is any surrogate left unrestored? (Zero by construction; checked anyway.)
"""

from __future__ import annotations

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

    def event(self, seq: int) -> LeakCheck:
        leaks = list(self.invented) + [
            DetectedSpan(start=0, end=0, text=t, type="DIRECT", category="ECHO", detector="vault")
            for t in self.original_echoed
        ]
        return LeakCheck(seq=seq, passed=self.passed, leaks=leaks)


def leak_check(
    raw_reply: str,
    restored: Restored,
    vault: Vault,
    session: str,
    known_texts: set[str],
    use_presidio: bool = True,
    use_gliner: bool = True,
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
    invented = []
    for h in det.entities:
        if (
            h.category in DIRECT
            and h.category != "NAME"
            and h.text.lower() not in known
            and not any(h.text.lower() in k or k in h.text.lower() for k in known)
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
    passed = not echoed and not invented and not restored.unrestored_surrogates
    return LeakResult(
        passed=passed,
        original_echoed=echoed,
        invented=invented,
        unrestored=restored.unrestored_surrogates,
    )
