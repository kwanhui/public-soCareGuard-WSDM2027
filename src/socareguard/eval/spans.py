"""Span-level detection metrics against corpus gold spans.

Reports exact and relaxed (overlap) precision, recall and F1 per category and overall,
plus recall by name origin (the WSDM-relevance hook and a fairness finding), and
leakage rate: the share of gold DIRECT spans not covered by any detection, which is the
headline safety number. Conventions follow the de-identification literature (exact and
partial match as in the i2b2 shared tasks); Cohen's kappa is never reported for spans.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from socareguard.corpus.schema import Note, Span, SpanType


@dataclass(frozen=True)
class Pred:
    start: int
    end: int
    category: str
    score: float = 1.0


@dataclass
class PRF:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


@dataclass
class Report:
    exact: dict[str, PRF] = field(default_factory=dict)
    relaxed: dict[str, PRF] = field(default_factory=dict)
    recall_by_origin: dict[str, PRF] = field(default_factory=dict)
    leakage: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        n_direct = self.leakage.get("direct_gold", 0)
        return {
            "exact": {k: v.as_dict() for k, v in sorted(self.exact.items())},
            "relaxed": {k: v.as_dict() for k, v in sorted(self.relaxed.items())},
            "recall_by_origin": {
                k: {"recall": round(v.recall, 4), "n": v.tp + v.fn}
                for k, v in sorted(self.recall_by_origin.items())
            },
            "leakage": {
                **self.leakage,
                "leakage_rate": round(self.leakage.get("direct_missed", 0) / n_direct, 4)
                if n_direct
                else 0.0,
            },
        }


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def _same_cat(g: str, p: str) -> bool:
    # Third-party names and client names are both names to a detector.
    names = {"NAME", "THIRD_PARTY_NAME"}
    return g == p or (g in names and p in names)


def score_note(
    note: Note,
    preds: Sequence[Pred],
    categories: Iterable[str] | None = None,
    min_score: float = 0.5,
) -> Report:
    """Score predictions for one note. ATTRIBUTE gold spans are excluded: they are
    generalisation targets, not detection targets."""
    gold = [s for s in note.spans if s.type is not SpanType.ATTRIBUTE]
    if categories:
        cats = set(categories)
        gold = [s for s in gold if s.category in cats]
    preds = [p for p in preds if p.score >= min_score]
    rep = Report()
    matched_exact: set[int] = set()
    matched_relaxed: set[int] = set()
    used_exact: set[int] = set()
    used_relaxed: set[int] = set()
    for gi, g in enumerate(gold):
        for pi, p in enumerate(preds):
            if not _same_cat(g.category, p.category):
                continue
            if pi not in used_exact and (g.start, g.end) == (p.start, p.end):
                matched_exact.add(gi)
                used_exact.add(pi)
            if pi not in used_relaxed and _overlap(g.start, g.end, p.start, p.end):
                matched_relaxed.add(gi)
                used_relaxed.add(pi)
    for mode, matched, used in (
        ("exact", matched_exact, used_exact),
        ("relaxed", matched_relaxed, used_relaxed),
    ):
        table = rep.exact if mode == "exact" else rep.relaxed
        for gi, g in enumerate(gold):
            cat = table.setdefault(g.category, PRF())
            allc = table.setdefault("ALL", PRF())
            if gi in matched:
                cat.tp += 1
                allc.tp += 1
            else:
                cat.fn += 1
                allc.fn += 1
        for pi, p in enumerate(preds):
            if pi not in used:
                table.setdefault(p.category, PRF()).fp += 1
                table.setdefault("ALL", PRF()).fp += 1
    for gi, g in enumerate(gold):
        if g.category in {"NAME", "THIRD_PARTY_NAME"} and g.origin:
            o = rep.recall_by_origin.setdefault(g.origin, PRF())
            if gi in matched_relaxed:
                o.tp += 1
            else:
                o.fn += 1
    direct = [gi for gi, g in enumerate(gold) if g.type is SpanType.DIRECT]
    rep.leakage = {
        "direct_gold": len(direct),
        "direct_missed": sum(1 for gi in direct if gi not in matched_relaxed),
    }
    return rep


def merge(reports: Iterable[Report]) -> Report:
    out = Report()
    for r in reports:
        for mode in ("exact", "relaxed", "recall_by_origin"):
            src, dst = getattr(r, mode), getattr(out, mode)
            for k, v in src.items():
                d = dst.setdefault(k, PRF())
                d.tp += v.tp
                d.fp += v.fp
                d.fn += v.fn
        for k, v in r.leakage.items():
            out.leakage[k] = out.leakage.get(k, 0) + v
    return out


def preds_from_spans(spans: Iterable[Span]) -> list[Pred]:
    """Turn gold spans into predictions (an oracle), used in tests."""
    return [Pred(s.start, s.end, s.category) for s in spans if s.type is not SpanType.ATTRIBUTE]
