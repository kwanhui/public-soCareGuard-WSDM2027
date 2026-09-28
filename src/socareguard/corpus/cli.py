"""python3 -m socareguard.corpus {generate,inject,drafts,sweep,stats,drafts-external,drafts-careteam}"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from socareguard.corpus import drafts as drafts_mod
from socareguard.corpus import generate as gen
from socareguard.corpus import inject as inj
from socareguard.corpus.schema import Note

PACKS = ("disability", "domestic-violence", "youth-offending")


def load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def load_notes(cfg: dict[str, Any], packs: tuple[str, ...]) -> list[Note]:
    notes: list[Note] = []
    for p in packs:
        f = Path(cfg["paths"]["notes"]) / f"{p}.jsonl"
        if f.exists():
            notes += [Note.model_validate_json(l) for l in f.read_text().splitlines() if l.strip()]
    return notes


def cmd_generate(a: argparse.Namespace, cfg: dict[str, Any]) -> None:
    load_dotenv()
    for p in a.packs:
        out = gen.generate_pack(p, cfg, Path(cfg["paths"]["templates"]), limit=a.limit)
        ts = gen.load_templates(out)
        bad = [t.id for t in ts if t.validation_errors]
        print(f"{p}: {len(ts)} templates, {len(bad)} invalid -> {out}")


def cmd_inject(a: argparse.Namespace, cfg: dict[str, Any]) -> None:
    for p in a.packs:
        src = Path(cfg["paths"]["templates"]) / f"{p}.jsonl"
        if not src.exists():
            print(f"{p}: no templates at {src}", file=sys.stderr)
            continue
        notes = [inj.inject(t) for t in gen.load_templates(src) if not t.validation_errors]
        out = Path(cfg["paths"]["notes"]) / f"{p}.jsonl"
        gen.dump_jsonl(notes, out)
        print(f"{p}: {len(notes)} notes, {sum(len(n.spans) for n in notes)} spans -> {out}")


def cmd_drafts(a: argparse.Namespace, cfg: dict[str, Any]) -> None:
    load_dotenv()
    for p in a.packs:
        notes = load_notes(cfg, (p,))
        if not notes:
            print(f"{p}: no notes", file=sys.stderr)
            continue
        out = drafts_mod.draft_pack(
            notes, cfg, Path(cfg["paths"]["drafts"]) / f"{p}.jsonl", limit=a.limit
        )
        ds = drafts_mod.load_drafts(out)
        print(f"{p}: {len(ds)} drafts {drafts_mod.label_counts(ds)} -> {out}")


def cmd_drafts_external(a: argparse.Namespace, cfg: dict[str, Any]) -> None:
    """Corpus v1.2: compliant drafts for an external reader (referral notes, school and employer
    letters that stay within need-to-know), appended as new files beside the v1.1 drafts."""
    notes = {p: load_notes(cfg, (p,)) for p in a.packs}
    if a.estimate:
        print(json.dumps(drafts_mod.estimate_external(notes, cfg), indent=1))
        return
    load_dotenv()
    for p, ns in notes.items():
        out = drafts_mod.draft_external_pack(ns, cfg)
        ds = drafts_mod.load_drafts(out)
        tasks: dict[str, int] = {}
        for d in ds:
            tasks[d.task] = tasks.get(d.task, 0) + 1
        print(f"{p}: {len(ds)} external drafts {tasks} -> {out}")


def cmd_drafts_careteam(a: argparse.Namespace, cfg: dict[str, Any]) -> None:
    """Corpus v1.3: compliant drafts for the client's own care team (a day activity centre, the
    client's clinic, a shelter caseworker, a polyclinic doctor, a school counsellor, a co-case
    agency worker), appended as new files beside the earlier drafts."""
    notes = {p: load_notes(cfg, (p,)) for p in a.packs}
    if a.estimate:
        print(json.dumps(drafts_mod.estimate_careteam(notes, cfg), indent=1))
        return
    load_dotenv()
    for p, ns in notes.items():
        out = drafts_mod.draft_careteam_pack(ns, cfg)
        ds = drafts_mod.load_drafts(out)
        tasks: dict[str, int] = {}
        for d in ds:
            tasks[d.task] = tasks.get(d.task, 0) + 1
        print(f"{p}: {len(ds)} care-team drafts {tasks} -> {out}")


def cmd_sweep(a: argparse.Namespace, cfg: dict[str, Any]) -> None:
    from socareguard.corpus import sweep as sw

    notes = load_notes(cfg, tuple(a.packs))
    cands = sw.sweep(notes, use_gliner=not a.no_gliner)
    sample = sw.audit_sample(notes, a.sample, int(cfg["seed"]))
    summary = sw.write_report(
        notes, cands, sample, Path("corpus/sweep-report.md"), Path("corpus/sweep-candidates.json")
    )
    print(json.dumps(summary, indent=2))


def cmd_stats(a: argparse.Namespace, cfg: dict[str, Any]) -> None:
    result: dict[str, Any] = {}
    for p in a.packs:
        notes = load_notes(cfg, (p,))
        if notes:
            result[p] = inj.span_stats(notes)
        df = Path(cfg["paths"]["drafts"]) / f"{p}.jsonl"
        if df.exists():
            result.setdefault(p, {})["drafts_by_label"] = drafts_mod.label_counts(
                drafts_mod.load_drafts(df)
            )
    allnotes = load_notes(cfg, tuple(a.packs))
    if allnotes:
        result["all"] = inj.span_stats(allnotes)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python3 -m socareguard.corpus")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="configs/corpus-v1.yaml", type=Path)
    common.add_argument("--packs", nargs="+", default=list(PACKS), choices=PACKS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser(
        "generate", parents=[common], help="layer 1: LLM-written templates with placeholders"
    )
    g.add_argument("--limit", type=int, default=None)
    sub.add_parser(
        "inject", parents=[common], help="layer 2: substitute surrogates and emit gold spans"
    )
    d = sub.add_parser(
        "drafts", parents=[common], help="layer 3: compliant and labelled-failure model drafts"
    )
    d.add_argument("--limit", type=int, default=None)
    s = sub.add_parser(
        "sweep", parents=[common], help="spontaneous-entity sweep with Presidio and GLiNER"
    )
    s.add_argument("--sample", type=int, default=30)
    s.add_argument("--no-gliner", action="store_true")
    sub.add_parser("stats", parents=[common], help="corpus statistics")
    de = sub.add_parser(
        "drafts-external",
        parents=[common],
        help="corpus v1.2: compliant external drafts (needs configs/corpus-v1.2.yaml)",
    )
    de.add_argument("--estimate", action="store_true", help="print the cost and call nothing")
    dc = sub.add_parser(
        "drafts-careteam",
        parents=[common],
        help="corpus v1.3: compliant care-team drafts (needs configs/corpus-v1.3.yaml)",
    )
    dc.add_argument("--estimate", action="store_true", help="print the cost and call nothing")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    {
        "generate": cmd_generate,
        "inject": cmd_inject,
        "drafts": cmd_drafts,
        "sweep": cmd_sweep,
        "stats": cmd_stats,
        "drafts-external": cmd_drafts_external,
        "drafts-careteam": cmd_drafts_careteam,
    }[a.cmd](a, cfg)


if __name__ == "__main__":
    main()
