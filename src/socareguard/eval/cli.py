"""python3 -m socareguard.eval {detect,roundtrip,utility,screen,report,auprc,rescore,rules}"""

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
    d.add_argument(
        "--variants",
        action="store_true",
        help="recall on the NRIC and FIN format-variant stress set (tests/data/nric-variants.jsonl)",
    )
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
    sc.add_argument(
        "--prompt-only",
        action="store_true",
        help="ablation: the same judge without the clause table, definitions and setting rules",
    )
    sc.add_argument(
        "--corpus",
        default=None,
        choices=["v1.1", "v1.2", "v1.3"],
        help="v1.2 adds the compliant external drafts and v1.3 the compliant care-team drafts, "
        "so the gated and ungated FPR on them is reported per tier (default v1.1, or the corpus "
        "of the --reuse-from run)",
    )
    sc.add_argument(
        "--care-team-only",
        action="store_true",
        help="judge only the drafts whose recipient_kind is care-team",
    )
    sc.add_argument(
        "--tier-off",
        action="store_true",
        help="judge care-team drafts with the plain prompt of an external draft, without the "
        "care-team paragraph (with --care-team-only: the tier-off comparison)",
    )
    sc.add_argument(
        "--reuse-from",
        default=None,
        metavar="TAG",
        help="copy the rows of screen-TAG-rows.jsonl whose judge prompt is unchanged, so that "
        "only the drafts whose prompt changed (the care-team drafts) are judged",
    )
    sc.add_argument(
        "--estimate",
        action="store_true",
        help="print the judge's input tokens and list-price cost for the run, and call nothing",
    )
    sub.add_parser("report", help="render docs/metrics.md from the JSON results")
    ap_ = sub.add_parser(
        "auprc", help="recompute tie-aware average precision from an earlier run's per-draft rows"
    )
    ap_.add_argument("--version", default="v1.1")
    rs = sub.add_parser(
        "rescore",
        help="score a v1.2 or v1.3 screen run's rows on the 600 v1.1 drafts only (no model call)",
    )
    rs.add_argument("--tag", required=True)
    ru = sub.add_parser(
        "rules",
        help="recompute the deterministic rules (over-caution, the I14 guard) on a screen run's rows "
        "and score it again (no model call)",
    )
    ru.add_argument("--tag", required=True)
    ru.add_argument(
        "--guard-scope",
        default="care-team",
        choices=["care-team", "all"],
        help="score the I14 guard on the care-team drafts only (results-v1.3) or on every row",
    )
    a = ap.parse_args(argv)
    if a.cmd == "screen":
        from socareguard.eval.run_screen import estimate
        from socareguard.eval.run_screen import run as run_screen
        from socareguard.screen.judge import DEFAULT_JUDGE_MODEL

        if a.corpus is None:
            src = Path("docs/metrics") / f"screen-{a.reuse_from}.json"
            src_corpus = (
                json.loads(src.read_text()).get("corpus") if a.reuse_from and src.exists() else None
            )
            a.corpus = src_corpus if src_corpus in ("v1.1", "v1.2", "v1.3") else "v1.1"
        if a.estimate:
            print(
                json.dumps(
                    estimate(
                        tuple(a.packs),
                        a.limit,
                        a.prompt_only,
                        corpus=a.corpus,
                        reuse_from=a.reuse_from,
                        care_team_only=a.care_team_only,
                        tier_off=a.tier_off,
                    ),
                    indent=1,
                )
            )
            return
        res = run_screen(
            tuple(a.packs),
            a.limit,
            a.judge or DEFAULT_JUDGE_MODEL,
            a.tag,
            use_baseline=not a.no_baseline,
            prompt_only=a.prompt_only,
            corpus=a.corpus,
            reuse_from=a.reuse_from,
            care_team_only=a.care_team_only,
            tier_off=a.tier_off,
        )
        print(
            json.dumps(
                {k: res.get(k) for k in ("drafts", "binary", "intended_label_recall", "baseline")},
                indent=1,
            )
        )
        return
    if a.cmd == "auprc":
        from socareguard.eval.run_screen import recompute_auprc

        res = recompute_auprc(a.version)
        print(json.dumps({k: {m: v[m] for m in ("auprc", "auprc_ungated_tie_aware",
              "auprc_file_order_deprecated", "distinct_scores")} for k, v in res["runs"].items()},
              indent=1))  # fmt: skip
        return
    if a.cmd == "rescore":
        from socareguard.eval.run_screen import rescore_v11_drafts

        res = rescore_v11_drafts(a.tag)
        print(
            json.dumps(
                {k: res.get(k) for k in ("drafts", "binary", "intended_label_recall")}, indent=1
            )
        )
        return
    if a.cmd == "rules":
        from socareguard.eval.run_screen import apply_rules

        res = apply_rules(a.tag, a.guard_scope)
        print(
            json.dumps({k: res.get(k) for k in ("drafts", "binary", "rules_recomputed")}, indent=1)
        )
        return
    if a.cmd == "report":
        from socareguard.eval.report import main as report_main

        report_main()
        return
    if a.cmd == "detect" and a.variants:
        from socareguard.eval.run_detect import run_variants

        res = run_variants(use_presidio=not a.no_presidio, use_gliner=not a.no_gliner, tag=a.tag)
        print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))
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
                    "leakage_matched": o["leakage_matched"],
                    "leakage_covered": o["leakage_covered"],
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
