"""Combine rules, the clause-grounded judge and the baseline into flags, a decision and events."""

from __future__ import annotations

from socareguard.policy.loader import Pack
from socareguard.scenarios.events import Action, Flag, Screen
from socareguard.screen import rules
from socareguard.screen.judge import Judge, JudgeFlag, LLMJudge
from socareguard.taxonomy import BY_ID

SEVERITY_ORDER = {"pass": 0, "info": 0, "annotate": 1, "regenerate": 2, "escalate": 3}
DECISION_FOR = {0: "pass", 1: "annotate", 2: "regenerate", 3: "escalate"}


class Screener:
    def __init__(
        self, judge: Judge | None = None, use_baseline: bool = True, min_confidence: float = 0.5
    ):
        self.judge = judge or LLMJudge()
        self.use_baseline = use_baseline
        self.min_confidence = min_confidence

    def flags_for(
        self, draft: str, pack: Pack, instruction: str, leaks: list | None = None, context: str = ""
    ) -> list[Flag]:
        out: list[Flag] = []
        oc = rules.over_caution(draft, instruction)
        if oc and pack.action_for("OVER_CAUTION"):
            out.append(oc.model_copy(update={"severity": pack.action_for("OVER_CAUTION")}))
        inv = rules.invented_identifiers(leaks or [])
        if inv and pack.action_for("I13"):
            out.append(inv.model_copy(update={"severity": pack.action_for("I13")}))
        external = rules.audience_is_external(instruction)
        for jf in self.judge(pack, instruction, draft, context):
            if jf.label in rules.AUDIENCE_DEPENDENT and not external:
                continue
            if jf.confidence < self.min_confidence or any(f.label == jf.label for f in out):
                continue
            action = pack.action_for(jf.label) or "annotate"
            out.append(
                Flag(
                    label=jf.label,
                    clause=BY_ID[jf.label].clause,
                    severity=action if action in SEVERITY_ORDER else "annotate",
                    evidence=jf.evidence,
                    rewrite=jf.rewrite,
                )
            )
        return out

    def screen(
        self,
        draft: str,
        pack: Pack,
        seq: int,
        instruction: str = "",
        leaks: list | None = None,
        context: str = "",
    ) -> tuple[list[Flag], str, list]:
        flags = self.flags_for(draft, pack, instruction, leaks, context)
        baseline: list[str] = []
        if self.use_baseline:
            from socareguard.screen.baseline import moderation_flags

            try:
                baseline = moderation_flags(draft)
            except Exception:  # noqa: BLE001 - the baseline must never block the request
                baseline = []
        level = max((SEVERITY_ORDER.get(f.severity, 1) for f in flags), default=0)
        decision = DECISION_FOR[level]
        return flags, decision, [Screen(seq=seq, flags=flags, baseline_flags=baseline)]


__all__ = ["Action", "JudgeFlag", "Screener"]
