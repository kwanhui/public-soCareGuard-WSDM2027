"""python3 -m socareguard.eval {detect,roundtrip,utility}"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from socareguard.corpus.schema import Note

PACKS = ("disability", "domestic-violence", "youth-offending")


def load_notes(packs, limit=None) -> list[Note]:
    notes: list[Note] = []
    for p in packs:
        f = Path("corpus/notes") / f"{p}.jsonl"
        rows = [Note.model_validate_json(l) for l in f.read_text().splitlines() if l.strip()]
        notes += rows[:limit] if limit else rows
    return notes


def main(argv=None) -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(prog="python3 -m socareguard.eval")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--packs", nargs="+", default=list(PACKS), choices=PACKS)
    common.add_argument("--limit", type=int, default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect", parents=[common])
    d.add_argument("--no-gliner", action="store_true")
    d.add_argument("--no-presidio", action="store_true")
    d.add_argument("--tag", default=None)
    r = sub.add_parser("roundtrip", parents=[common])
    r.add_argument("--tag", default="v1")
    u = sub.add_parser("utility", parents=[common])
    u.add_argument(
        "--providers", nargs="+", default=["openai/gpt-4.1-mini", "anthropic/claude-sonnet-5"]
    )
    u.add_argument("--tag", default="v1")
    sc = sub.add_parser("screen", parents=[common], help="screener metrics on the labelled drafts")
    sc.add_argument("--judge", default=None)
    sc.add_argument("--tag", default="v1")
    sc.add_argument("--no-baseline", action="store_true")
    sub.add_parser("report", help="render docs/metrics.md from the JSON results")
    a = ap.parse_args(argv)
    if a.cmd == "screen":
        from socareguard.eval.run_screen import run as run_screen
        from socareguard.screen.judge import DEFAULT_JUDGE_MODEL

        res = run_screen(
            tuple(a.packs),
            a.limit,
            a.judge or DEFAULT_JUDGE_MODEL,
            a.tag,
            use_baseline=not a.no_baseline,
        )
        print(
            json.dumps(
                {k: res[k] for k in ("drafts", "binary", "intended_label_recall", "baseline")},
                indent=1,
            )
        )
        return
    if a.cmd == "report":
        from socareguard.eval.report import main as report_main

        report_main()
        return
    notes = load_notes(a.packs, a.limit)
    if a.cmd == "detect":
        from socareguard.eval.run_detect import run

        tag = a.tag or (
            "sg-only"
            if a.no_gliner and a.no_presidio
            else "no-gliner"
            if a.no_gliner
            else "no-presidio"
            if a.no_presidio
            else "full"
        )
        res = run(notes, use_presidio=not a.no_presidio, use_gliner=not a.no_gliner, tag=tag)
        o = res["overall"]
        print(
            json.dumps(
                {
                    "tag": tag,
                    "notes": res["notes"],
                    "detectors": res["detectors"],
                    "relaxed_ALL": o["relaxed"]["ALL"],
                    "exact_ALL": o["exact"]["ALL"],
                    "leakage": o["leakage"],
                    "recall_by_origin": o["recall_by_origin"],
                    "attribute_recall": res["attribute_recall"],
                    "latency_s": res["latency_s"],
                },
                indent=1,
            )
        )
    elif a.cmd == "roundtrip":
        from socareguard.eval.run_roundtrip import run

        print(json.dumps(run(notes, a.tag), indent=1))
    else:
        from socareguard.eval.run_utility import run

        print(json.dumps(run(notes, a.providers, a.tag), indent=1))


if __name__ == "__main__":
    main()
