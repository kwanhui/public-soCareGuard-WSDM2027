"""Screener metrics on the labelled drafts.

For each draft: the clause-grounded judge's flags with confidences, the deterministic rules,
and the generic baseline (OpenAI moderation, optionally ExpGuard). Scores follow the safety-
classifier convention: F1, AUPRC and FPR together, binary (any conduct flag vs NONE) and per
label. Labels are generation-intent labels; see corpus/README.md.
"""

from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from socareguard.corpus.drafts import TASKS, load_drafts
from socareguard.corpus.schema import Draft, Note
from socareguard.policy.loader import load_pack
from socareguard.screen.judge import LLMJudge
from socareguard.screen.rules import AUDIENCE_DEPENDENT, audience_is_external, over_caution
from socareguard.taxonomy import BY_ID

OUT = Path("docs/metrics")


def average_precision(scores: list[float], labels: list[int]) -> float:
    """Average precision with ties processed together, as ``sklearn.metrics.
    average_precision_score`` computes it: one precision-recall point per distinct score, so the
    result does not depend on the order of the rows. The judge returns few distinct confidences,
    and a stable sort that walks tied rows one at a time scores them in file order."""
    pos = sum(labels)
    if pos == 0:
        return 0.0
    by_score: dict[float, list[int]] = {}
    for s, y in zip(scores, labels, strict=True):
        c = by_score.setdefault(s, [0, 0])
        c[0 if y else 1] += 1
    tp = fp = 0
    ap, prev_recall = 0.0, 0.0
    for s in sorted(by_score, reverse=True):
        tp += by_score[s][0]
        fp += by_score[s][1]
        recall, precision = tp / pos, tp / (tp + fp)
        ap += precision * (recall - prev_recall)
        prev_recall = recall
    return round(ap, 4)


def _auprc(scores: list[float], labels: list[int]) -> float:
    """Deprecated: walks tied scores in file order (kept for comparison with v1.1 files)."""
    pairs = sorted(zip(scores, labels, strict=True), key=lambda x: -x[0])
    tp = fp = 0
    pos = sum(labels)
    if pos == 0:
        return 0.0
    area, prev_recall = 0.0, 0.0
    for _, y in pairs:
        if y:
            tp += 1
        else:
            fp += 1
        recall, precision = tp / pos, tp / (tp + fp)
        area += precision * (recall - prev_recall)
        prev_recall = recall
    return round(area, 4)


def _prf(tp: int, fp: int, fn: int, tn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {
        "precision": round(p, 4),
        "recall": round(r, 4),
        "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
        "fpr": round(fp / (fp + tn), 4) if fp + tn else 0.0,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def load_screen_drafts(
    packs: tuple[str, ...], limit: int | None = None, corpus: str = "v1.1"
) -> list[Draft]:
    """The labelled drafts of a corpus version. v1.2 is the v1.1 drafts plus the compliant
    external drafts in corpus/drafts/<pack>-external-v1.2.jsonl; ``limit`` applies to the v1.1
    drafts of each pack, as before."""
    if corpus not in ("v1.1", "v1.2"):
        raise ValueError(f"unknown corpus {corpus}")
    drafts: list[Draft] = []
    for p in packs:
        rows = load_drafts(Path("corpus/drafts") / f"{p}.jsonl")
        drafts += rows[:limit] if limit else rows
        if corpus == "v1.2":
            drafts += load_drafts(Path("corpus/drafts") / f"{p}-external-v1.2.jsonl")
    return drafts


def judge_one(d: Draft, judge: LLMJudge, use_baseline: bool, note_text: str = "") -> dict[str, Any]:
    pack = load_pack(d.pack)
    instruction = TASKS[d.task]
    flags = judge(pack, instruction, d.text, note_text)
    oc = over_caution(d.text, instruction)
    row: dict[str, Any] = {
        "draft": d.id,
        "pack": d.pack,
        "task": d.task,
        "label": d.label.value,
        "judge_flags": {f.label: f.confidence for f in flags},
        "rule_over_caution": bool(oc),
        # None when the harm classifier was not run; a list (possibly empty) when it was
        "baseline": None,
    }
    if d.audience:
        row["audience"] = d.audience
    if use_baseline:
        from socareguard.screen.baseline import moderation_flags

        try:
            row["baseline"] = moderation_flags(d.text, threshold=0.3)
        except Exception:  # noqa: BLE001
            row["baseline"] = ["error"]
    return row


def run(
    packs: tuple[str, ...],
    limit: int | None,
    judge_model: str,
    tag: str,
    use_baseline: bool = True,
    workers: int = 4,
    prompt_only: bool = False,
    corpus: str = "v1.1",
) -> dict[str, Any]:
    drafts = load_screen_drafts(packs, limit, corpus)
    judge = LLMJudge(judge_model, prompt_only=prompt_only)
    notes: dict[str, str] = {}
    for p in packs:
        for line in (Path("corpus/notes") / f"{p}.jsonl").read_text().splitlines():
            if line.strip():
                n = Note.model_validate_json(line)
                notes[n.id] = n.text
    cache = OUT / f"screen-{tag}-rows.jsonl"
    done: dict[str, dict[str, Any]] = {}
    if cache.exists():
        for line in cache.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["draft"]] = r
    todo = [d for d in drafts if d.id not in done]
    with ThreadPoolExecutor(max_workers=workers) as ex, cache.open("a") as f:
        futs = {
            ex.submit(judge_one, d, judge, use_baseline, notes.get(d.note_id, "")): d for d in todo
        }
        for fut in as_completed(futs):
            r = fut.result()
            done[r["draft"]] = r
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    rows = [done[d.id] for d in drafts if d.id in done]
    res = summarise(rows, judge_model, tag, prompt_only=prompt_only, use_baseline=use_baseline)
    res["corpus"] = corpus
    if prompt_only:
        # the ablation's cost at list prices, recorded beside its result
        res["cost_estimate"] = estimate(packs, limit, prompt_only=True, corpus=corpus)
    (OUT / f"screen-{tag}.json").write_text(json.dumps(res, indent=2))
    return res


def estimate(
    packs: tuple[str, ...],
    limit: int | None,
    prompt_only: bool,
    output_tokens: int = 135,
    corpus: str = "v1.1",
    price_in: float = 2.0,
    price_out: float = 8.0,
) -> dict[str, Any]:
    """Judge input tokens (o200k_base) and list-price cost of a screen run, with no API call.
    Output tokens per call default to the runtime judge's estimate in docs/metrics/cost-v1.1.json;
    prices are gpt-4.1 standard-tier USD per million tokens on 2026-09-27."""
    import tiktoken

    from socareguard.screen.judge import build_prompt, build_prompt_only

    enc = tiktoken.get_encoding("o200k_base")
    notes: dict[str, str] = {}
    drafts = load_screen_drafts(packs, limit, corpus)
    for p in packs:
        for line in (Path("corpus/notes") / f"{p}.jsonl").read_text().splitlines():
            if line.strip():
                n = Note.model_validate_json(line)
                notes[n.id] = n.text
    total = 0
    for d in drafts:
        pack, ins, ctx = load_pack(d.pack), TASKS[d.task], notes.get(d.note_id, "")
        system, user = (
            build_prompt_only(pack, ins, d.text, ctx)
            if prompt_only
            else build_prompt(pack, ins, d.text, ctx)
        )
        total += len(enc.encode(system)) + len(enc.encode(user))
    n = len(drafts)
    usd = total * price_in / 1e6 + n * output_tokens * price_out / 1e6
    return {
        "drafts": n,
        "prompt_only": prompt_only,
        "input_tokens_total": total,
        "input_tokens_mean": round(total / n) if n else 0,
        "output_tokens_per_call_assumed": output_tokens,
        "usd_estimate": round(usd, 2),
    }


def row_is_external(r: dict[str, Any]) -> bool:
    """The audience of a scored draft: the draft's own label when the corpus records one (corpus
    v1.2), else what its task's instruction implies."""
    if r.get("audience") in ("internal", "external"):
        return r["audience"] == "external"
    return audience_is_external(TASKS[r["task"]])


def gated_flags(r: dict[str, Any]) -> dict[str, float]:
    """The judge's flags with the disclosure categories removed for an internal audience, plus the
    deterministic over-caution rule at confidence 1.0: the flags the operating points count."""
    external = row_is_external(r)
    out = {k: v for k, v in r["judge_flags"].items() if external or k not in AUDIENCE_DEPENDENT}
    if r["rule_over_caution"]:
        out["OVER_CAUTION"] = 1.0
    return out


def gated_score(r: dict[str, Any]) -> float:
    return max(gated_flags(r).values(), default=0.0)


def auprc_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Tie-aware average precision on the gated score, the number of distinct scores it ranks by,
    and the ungated file-order value that v1.1 reported, kept for comparison."""
    y = [0 if r["label"] == "NONE" else 1 for r in rows]
    gated = [gated_score(r) for r in rows]
    ungated = [
        max([*r["judge_flags"].values(), 1.0 if r["rule_over_caution"] else 0.0], default=0.0)
        for r in rows
    ]
    return {
        "auprc": average_precision(gated, y),
        "auprc_ungated_tie_aware": average_precision(ungated, y),
        "auprc_file_order_deprecated": _auprc(ungated, y),
        "distinct_scores": len(set(gated)),
    }


def summarise(
    rows: list[dict[str, Any]],
    judge_model: str,
    tag: str,
    prompt_only: bool = False,
    use_baseline: bool = True,
) -> dict[str, Any]:
    def flagged(r: dict[str, Any], thr: float = 0.5) -> set[str]:
        return {k for k, v in gated_flags(r).items() if v >= thr}

    # binary: is any conduct flag raised, vs generation-intent label NONE
    y = [0 if r["label"] == "NONE" else 1 for r in rows]
    pred = [1 if flagged(r) else 0 for r in rows]
    tp = sum(1 for a, b in zip(pred, y, strict=True) if a and b)
    fp = sum(1 for a, b in zip(pred, y, strict=True) if a and not b)
    fn = sum(1 for a, b in zip(pred, y, strict=True) if not a and b)
    tn = sum(1 for a, b in zip(pred, y, strict=True) if not a and not b)
    binary = {**_prf(tp, fp, fn, tn), **auprc_block(rows)}
    # the same operating point without the audience gate, so that the gate's effect on the
    # compliant drafts (all internal in v1.1, internal and external in v1.2) is visible
    ungated_pred = [
        1 if any(v >= 0.5 for v in r["judge_flags"].values()) or r["rule_over_caution"] else 0
        for r in rows
    ]
    binary["ungated"] = _prf(*_confusion(ungated_pred, y))
    by_audience: dict[str, Any] = {}
    for aud in ("internal", "external"):
        sel = [
            i
            for i, r in enumerate(rows)
            if r["label"] == "NONE" and (row_is_external(r) == (aud == "external"))
        ]
        if sel:
            by_audience[aud] = {
                "compliant_drafts": len(sel),
                "fpr_gated": round(sum(pred[i] for i in sel) / len(sel), 4),
                "fpr_ungated": round(sum(ungated_pred[i] for i in sel) / len(sel), 4),
            }
    binary["compliant_by_audience"] = by_audience
    # exact label match: the intended failure is among the flags raised
    intended_hit = sum(1 for r in rows if r["label"] != "NONE" and r["label"] in flagged(r))
    intended_n = sum(1 for r in rows if r["label"] != "NONE")
    per_label: dict[str, Any] = {}
    for lab in sorted({r["label"] for r in rows if r["label"] != "NONE"}):
        yl = [1 if r["label"] == lab else 0 for r in rows]
        sl = [gated_flags(r).get(lab, 0.0) for r in rows]
        sl_old = [
            r["judge_flags"].get(
                lab, 1.0 if (lab == "OVER_CAUTION" and r["rule_over_caution"]) else 0.0
            )
            for r in rows
        ]
        pl = [1 if lab in flagged(r) else 0 for r in rows]
        tp = sum(1 for a, b in zip(pl, yl, strict=True) if a and b)
        fp = sum(1 for a, b in zip(pl, yl, strict=True) if a and not b)
        fn = sum(1 for a, b in zip(pl, yl, strict=True) if not a and b)
        tn = sum(1 for a, b in zip(pl, yl, strict=True) if not a and not b)
        per_label[lab] = {
            "name": BY_ID[lab].name,
            **_prf(tp, fp, fn, tn),
            "auprc": average_precision(sl, yl),
            "auprc_file_order_deprecated": _auprc(sl_old, yl),
        }
    # baseline contrast (H1): generic harm classifier on the same drafts. A row whose baseline is
    # None was not sent to the classifier (a run with --no-baseline).
    base_rows = [
        r for r in rows if isinstance(r.get("baseline"), list) and r["baseline"] != ["error"]
    ]
    base_flag = [1 if r["baseline"] else 0 for r in base_rows]
    yb = [0 if r["label"] == "NONE" else 1 for r in base_rows]
    btp = sum(1 for a, b in zip(base_flag, yb, strict=True) if a and b)
    bfp = sum(1 for a, b in zip(base_flag, yb, strict=True) if a and not b)
    bfn = sum(1 for a, b in zip(base_flag, yb, strict=True) if not a and b)
    btn = sum(1 for a, b in zip(base_flag, yb, strict=True) if not a and not b)
    screener_only = sum(
        1 for r in base_rows if r["label"] != "NONE" and flagged(r) and not r["baseline"]
    )
    both = sum(1 for r in base_rows if r["label"] != "NONE" and flagged(r) and r["baseline"])
    baseline_only = sum(
        1 for r in base_rows if r["label"] != "NONE" and not flagged(r) and r["baseline"]
    )
    sweep = {}
    for thr in (0.5, 0.7, 0.85, 0.95):
        pt = [1 if flagged(r, thr) else 0 for r in rows]
        stp = sum(1 for a, b in zip(pt, y, strict=True) if a and b)
        sfp = sum(1 for a, b in zip(pt, y, strict=True) if a and not b)
        sfn = sum(1 for a, b in zip(pt, y, strict=True) if not a and b)
        stn = sum(1 for a, b in zip(pt, y, strict=True) if not a and not b)
        sweep[str(thr)] = _prf(stp, sfp, sfn, stn)
    result = {
        "tag": tag,
        "judge_model": judge_model,
        "judge_prompt": (
            "prompt-only: category ids and names, no clause table, definitions or setting rules"
            if prompt_only
            else "clause-grounded: the pack's SASW clause table, setting rules and guidance"
        ),
        "threshold_sweep": sweep,
        "drafts": len(rows),
        "failure_drafts": intended_n,
        "compliant_drafts": len(rows) - intended_n,
        "binary": binary,
        "intended_label_recall": round(intended_hit / intended_n, 4) if intended_n else None,
        "per_label": per_label,
        "baseline": {
            "name": "openai omni-moderation-latest (any category >= 0.3)",
            "n": len(base_rows),
            **_prf(btp, bfp, bfn, btn),
            "failure_drafts_flagged_by": {
                "screener_only": screener_only,
                "both": both,
                "baseline_only": baseline_only,
                "neither": sum(
                    1
                    for r in base_rows
                    if r["label"] != "NONE" and not flagged(r) and not r["baseline"]
                ),
            },
        },
        "per_pack": {
            p: _prf(*_counts([r for r in rows if r["pack"] == p], flagged))
            for p in sorted({r["pack"] for r in rows})
        },
    }
    if not use_baseline or not base_rows:
        result["baseline"] = None  # not run: no block for a classifier that saw no draft
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"screen-{tag}.json").write_text(json.dumps(result, indent=2))
    with (OUT / f"screen-{tag}.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "scope",
                "label",
                "name",
                "precision",
                "recall",
                "f1",
                "fpr",
                "auprc",
                "tp",
                "fp",
                "fn",
                "tn",
            ]
        )
        w.writerow(
            [
                "all",
                "ANY",
                "any conduct flag vs NONE",
                binary["precision"],
                binary["recall"],
                binary["f1"],
                binary["fpr"],
                binary["auprc"],
                binary["tp"],
                binary["fp"],
                binary["fn"],
                binary["tn"],
            ]
        )
        for lab, v in per_label.items():
            w.writerow(
                [
                    "all",
                    lab,
                    v["name"],
                    v["precision"],
                    v["recall"],
                    v["f1"],
                    v["fpr"],
                    v["auprc"],
                    v["tp"],
                    v["fp"],
                    v["fn"],
                    v["tn"],
                ]
            )
        b = result["baseline"] or {
            "name": "not run",
            **dict.fromkeys(("precision", "recall", "f1", "fpr", "tp", "fp", "fn", "tn"), ""),
        }
        w.writerow(
            [
                "baseline",
                "ANY",
                b["name"],
                b["precision"],
                b["recall"],
                b["f1"],
                b["fpr"],
                "",
                b["tp"],
                b["fp"],
                b["fn"],
                b["tn"],
            ]
        )
    return result


def _confusion(p: list[int], y: list[int]) -> tuple[int, int, int, int]:
    tp = sum(1 for a, b in zip(p, y, strict=True) if a and b)
    fp = sum(1 for a, b in zip(p, y, strict=True) if a and not b)
    fn = sum(1 for a, b in zip(p, y, strict=True) if not a and b)
    tn = sum(1 for a, b in zip(p, y, strict=True) if not a and not b)
    return tp, fp, fn, tn


def _counts(rows: list[dict[str, Any]], flagged) -> tuple[int, int, int, int]:
    y = [0 if r["label"] == "NONE" else 1 for r in rows]
    p = [1 if flagged(r) else 0 for r in rows]
    tp = sum(1 for a, b in zip(p, y, strict=True) if a and b)
    fp = sum(1 for a, b in zip(p, y, strict=True) if a and not b)
    fn = sum(1 for a, b in zip(p, y, strict=True) if not a and b)
    tn = sum(1 for a, b in zip(p, y, strict=True) if not a and not b)
    return tp, fp, fn, tn


def recompute_auprc(version: str = "v1.1") -> dict[str, Any]:
    """Tie-aware average precision recomputed from the per-draft rows of an earlier screen run,
    with no model call: the clause-grounded run, the prompt-only ablation and the second judge.
    Writes docs/metrics/auprc-tieaware-<version>.json."""
    runs = {
        "clause_grounded": f"screen-{version}-rows.jsonl",
        "prompt_only": f"screen-{version}-prompt-only-rows.jsonl",
        "second_judge": f"screen-{version}-claude-rows.jsonl",
    }
    out: dict[str, Any] = {
        "version": version,
        "method": (
            "average precision with tied scores processed together (sklearn "
            "average_precision_score semantics) on the audience-gated score: the maximum judge "
            "confidence over the flags that the operating points count, with the over-caution rule "
            "at 1.0 and I10 and I14 removed for an internal audience; distinct_scores counts the "
            "gated scores, 0.0 for an unflagged draft included"
        ),
        "runs": {},
    }
    for name, f in runs.items():
        p = OUT / f
        if not p.exists():
            continue
        rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        labels = sorted({r["label"] for r in rows if r["label"] != "NONE"})
        per_label = {}
        for lab in labels:
            yl = [1 if r["label"] == lab else 0 for r in rows]
            got = sum(1 for r in rows if r["label"] == lab and gated_flags(r).get(lab, 0) >= 0.5)
            per_label[lab] = {
                "auprc": average_precision([gated_flags(r).get(lab, 0.0) for r in rows], yl),
                "recall_at_0.5": f"{got} of {sum(yl)}",
            }
        out["runs"][name] = {
            "rows": f,
            "drafts": len(rows),
            **auprc_block(rows),
            "per_label": per_label,
        }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"auprc-tieaware-{version}.json").write_text(json.dumps(out, indent=2))
    return out


def rescore_v11_drafts(tag: str) -> dict[str, Any]:
    """Score the rows of a corpus v1.2 run on the 600 drafts of corpus v1.1 only, with no model
    call, so that its numbers compare like for like with a v1.1 run. The 90 external drafts carry
    ``audience`` in their rows and are dropped. Writes docs/metrics/screen-<tag>-v1.1-drafts.json."""
    src = OUT / f"screen-{tag}.json"
    meta = json.loads(src.read_text()) if src.exists() else {}
    external = {
        json.loads(line)["id"]
        for f in Path("corpus/drafts").glob("*-external-v1.2.jsonl")
        for line in f.read_text().splitlines()
        if line.strip()
    }
    rows = [
        json.loads(line)
        for line in (OUT / f"screen-{tag}-rows.jsonl").read_text().splitlines()
        if line.strip()
    ]
    rows = [r for r in rows if r["draft"] not in external]
    prompt_only = meta.get("judge_prompt", "").startswith("prompt-only")
    use_baseline = meta.get("baseline") is not None
    res = summarise(
        rows,
        meta.get("judge_model", ""),
        f"{tag}-v1.1-drafts",
        prompt_only=prompt_only,
        use_baseline=use_baseline,
    )
    res["corpus"] = "v1.1 drafts of a v1.2 run"
    res["rows"] = f"screen-{tag}-rows.jsonl"
    (OUT / f"screen-{tag}-v1.1-drafts.json").write_text(json.dumps(res, indent=2))
    return res
