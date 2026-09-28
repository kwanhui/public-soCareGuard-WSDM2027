"""Spontaneous-entity sweep.

The generator is told to write only placeholders, but it will sometimes invent a name,
a school or a number in free text. Those are real identifiers with no gold span and
they silently corrupt precision. This module runs off-the-shelf detectors over the
injected notes, lists every detection that does not overlap a gold span, and writes a
report plus a manual audit checklist for a fixed random sample of notes.

Requires the ``detect`` extra (presidio-analyzer, spacy, gliner).
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from socareguard.corpus.schema import Note

# Generic public bodies and vocabulary that detectors flag as ORG/PERSON but are not identifiers.
ALLOWLIST = {
    "msf",
    "moe",
    "comcare",
    "sso",
    "imh",
    "youth court",
    "family justice courts",
    "police",
    "fsc",
    "hdb",
    "cpf",
    "sasw",
    "ppo",
    "nric",
    "ite",
    "polyclinic",
    "mrt",
    "sgd",
    "singapore",
    "yishun",
    "mendaki",
    "sinda",
    "cdac",
    "aic",
    "ncss",
    "spf",
    "sgh",
    "nuh",
    "ttsh",
    "ktph",
    "cgh",
}

GLINER_LABELS = [
    "person",
    "organization",
    "location",
    "school",
    "phone number",
    "date of birth",
    "national id",
    "address",
    "case reference",
    "email",
]


@dataclass
class Candidate:
    note_id: str
    start: int
    end: int
    text: str
    label: str
    detector: str
    score: float


def _overlaps(start: int, end: int, note: Note) -> bool:
    return any(s.start < end and start < s.end for s in note.spans)


# Dates of contact and durations are not annotated in corpus v1 and are not identifiers the
# generator could have invented, so DATE_TIME is excluded from the sweep.
IGNORED_LABELS = {"DATE_TIME"}


def _plausible(text: str) -> bool:
    """A spontaneous identifier has a capital letter or a digit; 'client' or 'school' does not."""
    t = text.strip()
    return t.lower() not in ALLOWLIST and any(c.isupper() or c.isdigit() for c in t)


def _presidio(notes: list[Note]) -> list[Candidate]:
    from presidio_analyzer import AnalyzerEngine

    engine = AnalyzerEngine()
    out: list[Candidate] = []
    for n in notes:
        for r in engine.analyze(text=n.text, language="en"):
            if r.score < 0.4 or r.entity_type in IGNORED_LABELS or _overlaps(r.start, r.end, n):
                continue
            t = n.text[r.start : r.end]
            if not _plausible(t):
                continue
            out.append(
                Candidate(n.id, r.start, r.end, t, r.entity_type, "presidio", float(r.score))
            )
    return out


def _gliner(notes: list[Note], model_name: str) -> list[Candidate]:
    from gliner import GLiNER

    model = GLiNER.from_pretrained(model_name)
    out: list[Candidate] = []
    for n in notes:
        for e in model.predict_entities(n.text, GLINER_LABELS, threshold=0.5):
            if _overlaps(e["start"], e["end"], n):
                continue
            t = e["text"]
            if not _plausible(t):
                continue
            out.append(
                Candidate(n.id, e["start"], e["end"], t, e["label"], "gliner", float(e["score"]))
            )
    return out


def sweep(
    notes: list[Note], gliner_model: str = "urchade/gliner_multi_pii-v1", use_gliner: bool = True
) -> list[Candidate]:
    cands = _presidio(notes)
    if use_gliner:
        cands += _gliner(notes, gliner_model)
    return sorted(cands, key=lambda c: (c.note_id, c.start))


def audit_sample(notes: list[Note], k: int, seed: int) -> list[Note]:
    rng = random.Random(seed)
    return sorted(rng.sample(notes, min(k, len(notes))), key=lambda n: n.id)


def write_report(
    notes: list[Note], cands: list[Candidate], sample: list[Note], out_md: Path, out_json: Path
) -> dict[str, Any]:
    by_note: dict[str, list[Candidate]] = {}
    for c in cands:
        by_note.setdefault(c.note_id, []).append(c)
    flagged = sorted(by_note)
    summary = {
        "notes": len(notes),
        "notes_with_candidates": len(flagged),
        "candidate_rate": round(len(flagged) / max(len(notes), 1), 4),
        "candidates": len(cands),
        "by_label": {},
        "audit_sample_size": len(sample),
        "audit_sample_ids": [n.id for n in sample],
        "audit_sample_with_candidates": sum(1 for n in sample if n.id in by_note),
    }
    for c in cands:
        summary["by_label"][c.label] = summary["by_label"].get(c.label, 0) + 1
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(
            {"summary": summary, "candidates": [asdict(c) for c in cands]},
            indent=2,
            ensure_ascii=False,
        )
    )
    lines = [
        "# Spontaneous-entity sweep report",
        "",
        "Detections by off-the-shelf detectors that do not overlap any gold span. Each is either a",
        "spontaneous identifier the generator invented (a gold-span gap to fix) or a detector false",
        "positive (no action). The audit checklist below is a fixed random sample for manual review.",
        "",
        f"- Notes swept: {summary['notes']}",
        f"- Notes with at least one candidate: {summary['notes_with_candidates']} ({summary['candidate_rate']:.1%})",
        f"- Candidates: {summary['candidates']}",
        f"- By detector label: {json.dumps(summary['by_label'])}",
        "",
        "## Candidates",
        "",
        "| note | span | text | label | detector | score |",
        "|---|---|---|---|---|---|",
    ]
    for c in cands:
        lines.append(
            f"| {c.note_id} | {c.start}-{c.end} | {c.text.replace('|', '/')} | {c.label} | {c.detector} | {c.score:.2f} |"
        )
    lines += ["", f"## Manual audit checklist ({len(sample)} notes, fixed seed)", ""]
    for n in sample:
        mark = "candidates above" if n.id in by_note else "no candidates"
        lines.append(
            f"- [ ] {n.id} ({mark}): read the full note and confirm every identifier is inside a gold span"
        )
    out_md.write_text("\n".join(lines) + "\n")
    return summary
