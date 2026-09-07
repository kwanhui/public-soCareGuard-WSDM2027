"""Combine rules, the clause-grounded judge and the baseline into flags, a decision and events."""

from __future__ import annotations

from socareguard.policy.loader import Pack
from socareguard.scenarios.events import Action, Flag, Screen
from socareguard.screen import rules
from socareguard.screen.judge import Judge, JudgeFlag, LLMJudge
from socareguard.taxonomy import BY_ID

SEVERITY_ORDER = {"pass": 0, "info": 0, "annotate": 1, "regenerate": 2, "escalate": 3}


def _name_of(label: str) -> str:
    c = BY_ID.get(label)
    return c.name if c else label


DECISION_FOR = {0: "pass", 1: "annotate", 2: "regenerate", 3: "escalate"}


class Screener:
    def __init__(
        self, judge: Judge | None = None, use_baseline: bool = True, min_confidence: float = 0.5
    ):
        self.judge = judge or LLMJudge()
        self.use_baseline = use_baseline
        self.min_confidence = min_confidence

    def flags_for(
        self,
        draft: str,
        pack: Pack,
        instruction: str,
        leaks: list | None = None,
        context: str = "",
        audience: str | None = None,
    ) -> list[Flag]:
        out: list[Flag] = []
        oc = rules.over_caution(draft, instruction)
        if oc and pack.action_for("OVER_CAUTION"):
            out.append(oc.model_copy(update={"severity": pack.action_for("OVER_CAUTION")}))
        inv = rules.invented_identifiers(leaks or [])
        if inv and pack.action_for("I13"):
            out.append(inv.model_copy(update={"severity": pack.action_for("I13")}))
        external = (
            audience == "external"
            if audience in ("internal", "external")
            else rules.audience_is_external(instruction, pack.id)
        )
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
                    name=BY_ID[jf.label].name,
                    reason=getattr(jf, "reason", "") or "",
                    confidence=round(float(jf.confidence), 2),
                )
            )
        return [f.model_copy(update={"name": f.name or _name_of(f.label)}) for f in out]

    def screen(
        self,
        draft: str,
        pack: Pack,
        seq: int,
        instruction: str = "",
        leaks: list | None = None,
        context: str = "",
        audience: str | None = None,
    ) -> tuple[list[Flag], str, list]:
        flags = self.flags_for(draft, pack, instruction, leaks, context, audience)
        external = (
            audience == "external"
            if audience in ("internal", "external")
            else rules.audience_is_external(instruction, pack.id)
        )
        baseline: list[str] = []
        if self.use_baseline:
            from socareguard.screen.baseline import moderation_flags

            try:
                baseline = moderation_flags(draft)
            except Exception:  # noqa: BLE001 - the baseline must never block the request
                baseline = []
        level = max((SEVERITY_ORDER.get(f.severity, 1) for f in flags), default=0)
        decision = DECISION_FOR[level]
        return (
            flags,
            decision,
            [
                Screen(
                    seq=seq,
                    flags=flags,
                    baseline_flags=baseline,
                    judge_model=getattr(self.judge, "model", None),
                    baseline_model=self.baseline_model,
                    audience="external" if external else "internal",
                )
            ],
        )

    @property
    def baseline_model(self) -> str | None:
        import os

        if self.use_baseline and os.environ.get("OPENAI_API_KEY"):
            return "openai/omni-moderation-latest"
        return None


__all__ = ["Action", "JudgeFlag", "Screener"]
