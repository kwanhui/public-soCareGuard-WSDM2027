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
        # A young person named by the offence: I2 whatever the audience, before the judge, so a
        # judge I2 on the same draft does not replace the deterministic card.
        if pack.id == "youth-offending" and pack.action_for("I2"):
            lab = rules.offence_label(draft)
            if lab is not None:
                out.append(lab.model_copy(update={"severity": pack.action_for("I2")}))
        inv = rules.invented_identifiers(leaks or [])
        if inv and pack.action_for("I13"):
            # a hit from a general pattern alone never raises the decision above annotate, so it
            # cannot turn a draft the judge passed into a regeneration
            action = pack.action_for("I13") if inv.severity == "regenerate" else "annotate"
            out.append(inv.model_copy(update={"severity": action}))
        # The audience is resolved once per request, by the caller; a direct call without one
        # reads it from the instruction here. A care-team recipient is outside the case team, so
        # I10 and I14 apply to it as to any external recipient.
        if audience not in rules.AUDIENCES:
            audience = rules.resolve_audience(instruction, pack.id)
        external = audience != "internal"
        # Case closure with possibly unresolved risk: a hint to the judge, which decides.
        closure = None
        if pack.action_for("I6"):
            closure = rules.closure_with_unresolved_risk(draft, context, instruction)
        hints = [rules.CLOSURE_HINT] if closure else []
        # Initials beside a school, an age or an offence identify a young person to an external
        # recipient: a hint to the judge for I14, which decides.
        if external and pack.id == "youth-offending" and pack.action_for("I14"):
            ini = rules.initials_hint(draft)
            if ini:
                hints.append(ini)
        # Only a care-team draft changes the judge's call (one added paragraph in its prompt), so
        # the prompt for an internal or external draft is the same as before the tier existed.
        extra: dict = {"hints": hints} if hints else {}
        if audience == "care-team":
            extra["audience"] = audience
            extra["care_team_kind"] = rules.care_team_kind(instruction, pack.id)
        judged = self.judge(pack, instruction, draft, context, **extra)
        for jf in judged:
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
        # The I14 guard, after the judge: under the youth pack, a young person named alongside the
        # offence, the school, the age or a Youth Court reference for a recipient outside the
        # agency is I14 whatever the judge returned, because the care-team tier relaxes I10 only.
        # The card carries no confidence and a reason that opens "Deterministic check:", as the
        # offence-label card does.
        if external and pack.action_for("I14") and not any(f.label == "I14" for f in out):
            guard = rules.cypa_guard(draft, pack.id, audience)
            if guard is not None:
                out.append(guard.model_copy(update={"severity": pack.action_for("I14")}))
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
        if audience not in rules.AUDIENCES:
            audience = rules.resolve_audience(instruction, pack.id)
        flags = self.flags_for(draft, pack, instruction, leaks, context, audience)
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
                    audience=audience,
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
