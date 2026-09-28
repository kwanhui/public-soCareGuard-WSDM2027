"""Render docs/metrics.md from the JSON files under docs/metrics/.

python3 -m socareguard.eval report
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

OUT = Path("docs/metrics")


def _load(name: str) -> dict | None:
    p = OUT / name
    return json.loads(p.read_text()) if p.exists() else None


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


# Result files per corpus version. v1 holds the numbers of the first paper draft, v1.1 the numbers
# tagged results-v1.1, and v1.2 the re-measurement on corpus v1.2 (tag results-v1.2). All are kept
# so that the comparison below can be rendered.
FILES = {
    "v1": {
        "full": "detect-full.json",
        "ng": "detect-no-gliner.json",
        "sg": "detect-sg-only.json",
        "rt": "roundtrip-v1.json",
        "ut": "utility-v1.json",
        "sc": "screen-v1.json",
        "scc": "screen-v1-claude.json",
    },
    "v1.1": {
        "full": "detect-full-v1.1.json",
        "ng": "detect-no-gliner-v1.1.json",
        "sg": "detect-sg-only-v1.1.json",
        "rt": "roundtrip-v1.1.json",
        "ut": "utility-v1.1.json",
        "sc": "screen-v1.1.json",
        "scc": "screen-v1.1-claude.json",
    },
    "v1.2": {
        "full": "detect-full-v1.2.json",
        "ng": "detect-no-gliner-v1.2.json",
        "sg": "detect-sg-only-v1.2.json",
        "rt": "roundtrip-v1.2.json",
        "ut": "utility-v1.2.json",
        "sc": "screen-v1.2.json",
        "scc": "screen-v1.2-claude.json",
    },
}

# The result set this page reports; the earlier ones appear in the comparison table at the end.
CURRENT = "v1.2"


def _leak(overall: dict) -> dict:
    """Matched leakage; files written before the covered measure call it "leakage"."""
    return overall.get("leakage_matched") or overall["leakage"]


def _results(version: str) -> dict[str, dict | None]:
    return {k: _load(f) for k, f in FILES[version].items()}


def _pct2(x: float) -> str:
    return f"{100 * x:.2f}%"


def _pooled(table: dict, cats: tuple[str, ...]) -> str:
    tp, fp, fn = (sum(table[c][k] for c in cats if c in table) for k in ("tp", "fp", "fn"))
    p, r = tp / (tp + fp), tp / (tp + fn)
    return f"{p:.3f} / {r:.3f} / {2 * p * r / (p + r):.3f}"


def _saturation(version: str) -> str | None:
    """Judge flags at confidence 0.95 or above among all raw judge flags of a screen run (every draft of the run)."""
    p = OUT / f"screen-{version}-rows.jsonl"
    if not p.exists():
        return None
    vals = [
        v
        for line in p.read_text().splitlines()
        if line.strip()
        for v in json.loads(line)["judge_flags"].values()
    ]
    return f"{sum(1 for v in vals if v >= 0.95)} of {len(vals)}"


def _confidence_distribution(version: str) -> str | None:
    """Judge-flag confidence values on the 600 v1.1 drafts alone, so that the count of flags at
    or above 0.95 traces to a file (final-defensibility-read.md, 2026-09-28, item 1). Rows of the
    v1.2 external drafts carry ``"audience": "external"``; the v1.1 drafts carry no ``audience``
    key, so excluding "external" isolates the 600."""
    from collections import Counter

    p = OUT / f"screen-{version}-rows.jsonl"
    if not p.exists():
        return None
    rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    rows600 = [r for r in rows if r.get("audience") != "external"]
    vals = [v for r in rows600 for v in r["judge_flags"].values()]
    if not vals:
        return None
    counts = Counter(vals)
    dist = ", ".join(f"{k:g} ({n})" for k, n in sorted(counts.items()))
    n_hi = sum(n for k, n in counts.items() if k >= 0.95)
    return (
        f"Judge confidence distribution on the 600 v1.1 drafts alone ({len(rows600)} drafts, "
        f"{len(vals)} judge flags, from `screen-{version}-rows.jsonl`): {dist}. "
        f"At or above 0.95: {n_hi} of {len(vals)}."
    )


def _tie_aware(version: str, sc: dict) -> float | None:
    """Tie-aware average precision on the gated score: in the screen file from v1.2, recomputed
    from the rows (auprc-tieaware-<version>.json) for v1.1, not available for v1."""
    if "auprc_file_order_deprecated" in sc["binary"]:
        return sc["binary"]["auprc"]
    t = _load(f"auprc-tieaware-{version}.json")
    return t["runs"]["clause_grounded"]["auprc"] if t else None


def _v11_drafts_rows(sc: dict, version: str) -> list[tuple[str, str]]:
    """The screen on the 600 drafts of corpus v1.1 alone: the run itself up to v1.1, the rescored
    rows of the v1.2 run (``eval rescore``) from v1.2, so that the two compare like for like."""
    out: list[tuple[str, str]] = []
    for label, main, sub in (
        ("Clause-grounded", sc, f"screen-{version}-v1.1-drafts.json"),
        (
            "Prompt-only",
            _load(f"screen-{version}-prompt-only.json"),
            f"screen-{version}-prompt-only-v1.1-drafts.json",
        ),
    ):
        d = _load(sub) or (main if main and main["drafts"] == 600 else None)
        if not d:
            continue
        pre = f"600 v1.1 drafts, {label}"
        for t in ("0.5", "0.85"):
            v = d["threshold_sweep"][t]
            out.append(
                (
                    f"{pre} t={t} P / R / F1 / FPR",
                    f"{v['precision']:.3f} / {v['recall']:.3f} / {v['f1']:.3f} / {v['fpr']:.3f}",
                )
            )
        ta = (
            _tie_aware(version, d)
            if label == "Clause-grounded"
            else (
                d["binary"]["auprc"]
                if "auprc_file_order_deprecated" in d["binary"]
                else (_load(f"auprc-tieaware-{version}.json") or {})
                .get("runs", {})
                .get("prompt_only", {})
                .get("auprc")
            )
        )
        out.append(
            (f"{pre} average precision, tie-aware, gated", f"{ta:.3f}" if ta is not None else "n/a")
        )
        for lab in ("I1", "I10", "I11", "I14", "OVER_CAUTION"):
            v = d["per_label"].get(lab)
            if v:
                out.append(
                    (
                        f"{pre} {lab} P / R / F1",
                        f"{v['precision']:.3f} / {v['recall']:.3f} / {v['f1']:.3f}",
                    )
                )
        if label == "Clause-grounded":
            f1s = [v["f1"] for v in d["per_label"].values()]
            out.append((f"{pre} per-category F1, range", f"{min(f1s):.2f} to {max(f1s):.2f}"))
            out.append((f"{pre} intended-label recall", _pct(d["intended_label_recall"])))
            bl = d.get("baseline")
            if bl:
                fb = bl["failure_drafts_flagged_by"]
                out.append(
                    (
                        f"{pre} harm classifier P / R / F1 / FPR",
                        f"{bl['precision']:.3f} / {bl['recall']:.3f} / {bl['f1']:.3f} / {bl['fpr']:.3f}",
                    )
                )
                out.append(
                    (
                        f"{pre} failure drafts: screen only / classifier only / both / neither",
                        f"{fb['screener_only']} / {fb['baseline_only']} / {fb['both']} / {fb['neither']}",
                    )
                )
    return out


def _headline(r: dict[str, dict | None], version: str | None = None) -> list[tuple[str, str]]:
    """The numbers the paper reports, as (label, value) pairs."""
    out: list[tuple[str, str]] = []
    full, ng, sg, rt, ut, sc, scc = (r[k] for k in ("full", "ng", "sg", "rt", "ut", "sc", "scc"))
    if full:
        o = full["overall"]
        a, e = o["relaxed"]["ALL"], o["exact"]["ALL"]
        lk = _leak(o)
        out += [
            (
                "All spans, relaxed P / R / F1",
                f"{a['precision']:.3f} / {a['recall']:.3f} / {a['f1']:.3f}",
            ),
            (
                "All spans, exact P / R / F1",
                f"{e['precision']:.3f} / {e['recall']:.3f} / {e['f1']:.3f}",
            ),
            (
                "NRIC, phone, address, case ref., relaxed P / R / F1",
                _pooled(o["relaxed"], ("NRIC", "PHONE", "ADDRESS", "CASE_REF")),
            ),
            (
                "Names, relaxed P / R / F1",
                f"{o['relaxed']['NAME']['precision']:.3f} / {o['relaxed']['NAME']['recall']:.3f} / {o['relaxed']['NAME']['f1']:.3f}",
            ),
            ("Employer, relaxed recall", f"{o['relaxed']['EMPLOYER']['recall']:.3f}"),
            (
                "Leakage (matched), full pipeline",
                f"{_pct2(lk['leakage_rate'])} ({lk['direct_missed']} of {lk['direct_gold']})",
            ),
        ]
        if "leakage_covered" in o:
            c = o["leakage_covered"]
            out.append(
                (
                    "Leakage (covered), full pipeline",
                    f"{_pct2(c['leakage_rate'])} ({c['direct_uncovered']} of {c['direct_gold']})",
                )
            )
    if ng:
        out.append(
            ("Leakage (matched), without GLiNER2-PII", _pct2(_leak(ng["overall"])["leakage_rate"]))
        )
        if "leakage_covered" in ng["overall"]:
            out.append(
                (
                    "Leakage (covered), without GLiNER2-PII",
                    _pct2(ng["overall"]["leakage_covered"]["leakage_rate"]),
                )
            )
    if sg:
        out.append(
            ("Leakage (matched), recognisers only", _pct(_leak(sg["overall"])["leakage_rate"]))
        )
        if "leakage_covered" in sg["overall"]:
            out.append(
                (
                    "Leakage (covered), recognisers only",
                    _pct(sg["overall"]["leakage_covered"]["leakage_rate"]),
                )
            )
        sgn = sg["overall"]["relaxed"].get("NAME", {}).get("recall")
        if sgn is not None:
            out.append(("Name recall, recognisers only", f"{sgn:.3f}"))
    if full:
        rbo = full["overall"]["recall_by_origin"]
        ar = [v["recall"] for v in full["attribute_recall"].values()]
        out += [
            ("Name recall by origin", ", ".join(f"{k} {v['recall']:.3f}" for k, v in rbo.items())),
            ("Attribute recall by key, range", f"{min(ar):.2f} to {max(ar):.2f}"),
            ("Latency per note, p50", f"{full['latency_s']['p50']:.2f} s"),
        ]
    if rt:
        out.append(
            (
                "Gold direct strings in outbound text",
                f"{_pct2(rt['direct_leakage_rate'])} ({rt['direct_gold_leaked']} of {rt['direct_gold_total']})",
            )
        )
        if "attribute_verbatim_rate" in rt:
            out.append(
                (
                    "Gold attribute spans sent verbatim",
                    f"{_pct(rt['attribute_verbatim_rate'])} ({rt['attr_gold_leaked_verbatim']} of {rt['attr_gold_total']})",
                )
            )
    if sc:
        out.append(
            (
                "Screen drafts (failure / compliant)",
                f"{sc['drafts']} ({sc['failure_drafts']} / {sc['compliant_drafts']})",
            )
        )
        b, sw = sc["binary"], sc.get("threshold_sweep", {})
        out.append(
            (
                "Screen any flag t=0.5, P / R / F1 / FPR",
                f"{b['precision']:.3f} / {b['recall']:.3f} / {b['f1']:.3f} / {b['fpr']:.3f}",
            )
        )
        if "0.85" in sw:
            v = sw["0.85"]
            out.append(
                (
                    "Screen any flag t=0.85, P / R / F1 / FPR",
                    f"{v['precision']:.3f} / {v['recall']:.3f} / {v['f1']:.3f} / {v['fpr']:.3f}",
                )
            )
        out.append(
            (
                "Screen AUPRC, file order (deprecated)",
                f"{b.get('auprc_file_order_deprecated', b['auprc']):.3f}",
            )
        )
        ta = _tie_aware(version, sc) if version else None
        out.append(
            ("Screen average precision, tie-aware, gated", f"{ta:.3f}" if ta is not None else "n/a")
        )
        ung = b.get("ungated")
        if ung:
            out.append(
                (
                    "Screen any flag t=0.5 without the audience gate, P / R / F1 / FPR",
                    f"{ung['precision']:.3f} / {ung['recall']:.3f} / {ung['f1']:.3f} / {ung['fpr']:.3f}",
                )
            )
        for aud, v in b.get("compliant_by_audience", {}).items():
            out.append(
                (
                    f"FPR on {aud} compliant drafts, gated / ungated",
                    f"{v['fpr_gated']:.3f} / {v['fpr_ungated']:.3f} (n={v['compliant_drafts']})",
                )
            )
        bl, fb = sc["baseline"], sc["baseline"]["failure_drafts_flagged_by"]
        out.append(
            (
                "Harm classifier P / R / F1 / FPR",
                f"{bl['precision']:.3f} / {bl['recall']:.3f} / {bl['f1']:.3f} / {bl['fpr']:.3f}",
            )
        )
        out.append(
            (
                "Failure drafts: screen only / classifier only / both / neither",
                f"{fb['screener_only']} / {fb['baseline_only']} / {fb['both']} / {fb['neither']}",
            )
        )
        for lab in ("I7", "OVER_CAUTION", "I10"):
            v = sc["per_label"].get(lab)
            if v:
                out.append(
                    (
                        f"{lab} P / R / F1",
                        f"{v['precision']:.3f} / {v['recall']:.3f} / {v['f1']:.3f}",
                    )
                )
        f1s = [v["f1"] for v in sc["per_label"].values()]
        out.append(("Per-category F1, range", f"{min(f1s):.2f} to {max(f1s):.2f}"))
        out.append(("Intended-label recall", _pct(sc["intended_label_recall"])))
        sat = _saturation(version) if version else None
        if sat:
            out.append(("Judge flags at confidence 0.95 or above, all drafts of the run", sat))
        po = _load(f"screen-{version}-prompt-only.json") if version else None
        if po:
            pb, p85 = po["binary"], po["threshold_sweep"]["0.85"]
            out.append(("Prompt-only judge t=0.5 F1", f"{pb['f1']:.3f}"))
            out.append(("Prompt-only judge t=0.85 FPR", f"{p85['fpr']:.3f}"))
            out.append(
                (
                    "Prompt-only AUPRC, file order (deprecated)",
                    f"{pb.get('auprc_file_order_deprecated', pb['auprc']):.3f}",
                )
            )
            pta = (
                pb["auprc"]
                if "auprc_file_order_deprecated" in pb
                else (
                    (_load(f"auprc-tieaware-{version}.json") or {})
                    .get("runs", {})
                    .get("prompt_only", {})
                    .get("auprc")
                )
            )
            out.append(
                (
                    "Prompt-only average precision, tie-aware, gated",
                    f"{pta:.3f}" if pta is not None else "n/a",
                )
            )
            for lab in ("I10", "I11", "I14"):
                if lab in sc["per_label"] and lab in po["per_label"]:
                    out.append(
                        (
                            f"{lab} F1, clause-grounded / prompt-only",
                            f"{sc['per_label'][lab]['f1']:.2f} / {po['per_label'][lab]['f1']:.2f}",
                        )
                    )
    if sc and version and version != "v1":  # the v1 drafts are a different corpus
        out += _v11_drafts_rows(sc, version)
    if scc:
        out.append(
            (
                f"Second judge ({scc['judge_model']}, {scc['drafts']} drafts) F1",
                f"{scc['binary']['f1']:.3f}",
            )
        )
        c = scc["binary"]
        out.append(
            (
                "Second judge P / R / FPR",
                f"{c['precision']:.3f} / {c['recall']:.3f} / {c['fpr']:.3f}",
            )
        )
    if ut:
        for m, v in ut["providers"].items():
            for j, jv in v["by_judge"].items():
                out.append(
                    (f"Utility retention, provider {m}, judge {j}", _pct(jv["retention_rate"]))
                )
    return out


def _prompt_only_section(sc: dict, po: dict) -> list[str]:
    """The same judge without the clause table (WSDM Q4), beside the clause-grounded screen."""

    def row(name: str, d: dict) -> str:
        sw = d.get("threshold_sweep", {})
        a, b = sw.get("0.5", d["binary"]), sw.get("0.85", {})
        return (
            f"| {name} | {a['precision']:.3f} / {a['recall']:.3f} / {a['f1']:.3f} / {a['fpr']:.3f} | "
            + (
                f"{b['precision']:.3f} / {b['recall']:.3f} / {b['f1']:.3f} / {b['fpr']:.3f}"
                if b
                else "n/a"
            )
            + f" | {d['binary']['auprc']:.3f} | {_pct(d['intended_label_recall'])} |"
        )

    s5, p5 = sc["binary"], po["binary"]
    return [
        "## Prompt-only judge ablation",
        "",
        (
            f"To measure what the clause table adds, the same judge (`{po['judge_model']}` at temperature 0) was run on the same "
            f"{po['drafts']} drafts with a prompt that keeps the category ids and their plain names, so that its flags map onto the same labels, "
            "and removes the SASW clause text, the category definitions and guidance, and the pack's setting rules. "
            "The source note, the instruction, the output schema and the scoring are the same as for the clause-grounded screen, "
            "including the audience gate for I10 and I14 and the deterministic over-caution rule. "
            f"The clause-grounded row is the reported result set (`screen-{po['tag'].split('-prompt-only')[0]}.json`)."
        ),
        "",
        "| Judge prompt | t=0.5 P / R / F1 / FPR | t=0.85 P / R / F1 / FPR | AUPRC | Intended-label recall |",
        "|---|---|---|---|---|",
        row("Clause table, definitions and setting rules", sc),
        row("Category names only (prompt-only)", po),
        "",
        "Per-category F1, clause-grounded against prompt-only: "
        + ", ".join(
            f"{lab} {v['f1']:.2f} against {po['per_label'][lab]['f1']:.2f}"
            for lab, v in sc["per_label"].items()
            if lab in po["per_label"]
        )
        + ".",
        "",
        (
            f"At the 0.5 threshold, the prompt-only judge reaches F1 {p5['f1']:.3f} against {s5['f1']:.3f} for the clause-grounded judge, "
            f"with FPR {p5['fpr']:.3f} against {s5['fpr']:.3f} and AUPRC {p5['auprc']:.3f} against {s5['auprc']:.3f}. "
            f"At the 0.85 threshold, the FPR is {po['threshold_sweep']['0.85']['fpr']:.3f} against "
            f"{sc['threshold_sweep']['0.85']['fpr']:.3f}. "
            "Both runs share the generation-intent labels described above, so the difference is between two prompts on the same "
            "scripted material, not a validated accuracy gap. Produced by `python3 -m socareguard.eval screen --prompt-only --tag "
            f"{po['tag']} --no-baseline"
            + (f" --corpus {po['corpus']}`" if po.get("corpus", "v1.1") != "v1.1" else "`")
            + (
                f", at an estimated USD {po['cost_estimate']['usd_estimate']:.2f} at list prices "
                f"({po['cost_estimate']['input_tokens_mean']} input tokens per call counted with o200k_base, "
                f"{po['cost_estimate']['output_tokens_per_call_assumed']} output tokens per call assumed)."
                if po.get("cost_estimate")
                else "."
            )
        ),
        "",
    ]


def _variants_section(v: dict) -> list[str]:
    """Recall on the NRIC and FIN format-variant stress set (WSDM-N1, round 4)."""
    forms = ", ".join(f"{k} {c['covered']} of {c['total']}" for k, c in v["by_form"].items())
    return [
        "## NRIC and FIN format variants",
        "",
        (
            "The corpus writes every NRIC and FIN in the canonical form of the identifier factory in "
            "`corpus/identifiers.py`, which the deterministic recogniser also imports, so the NRIC row of the detection "
            "table is measured on that form only. "
            f"A separate stress set of {v['variants']} synthetic variants (`{v['file']}`) writes the number spaced, "
            'hyphenated, in lower case, after an "NRIC:" label, in parentheses, with a space on one side only and '
            "with a mistyped check letter."
        ),
        "",
        (
            f"Detectors: {', '.join(v['detectors'])}. Recall with an exact NRIC span: {_pct(v['recall_exact'])}; "
            f"recall with any overlapping direct-identifier span: {_pct(v['recall_covered'])}; "
            f"variants whose text survives in the sanitised note: {v['leaked']} of {v['variants']}. By form: {forms}."
        ),
        "Produced by `python3 -m socareguard.eval detect --variants`. Before round 4, the recogniser matched the compact form only.",
        "",
    ]


def _auprc_section(a: dict) -> list[str]:
    """Tie-aware average precision recomputed from the v1.1 rows (WSDM-N3, round 4)."""
    names = {
        "clause_grounded": "Clause-grounded judge",
        "prompt_only": "Prompt-only judge",
        "second_judge": "Second judge",
    }
    rows = [
        f"| {names[k]} | {r['drafts']} | {r['auprc']:.3f} | {r['auprc_ungated_tie_aware']:.3f} | "
        f"{r['auprc_file_order_deprecated']:.3f} | {r['distinct_scores']} |"
        for k, r in a["runs"].items()
    ]
    return [
        f"## Average precision with ties processed together ({a['version']} rows)",
        "",
        (
            "The judge returns few distinct confidence values, and the AUPRC reported in the v1.1 files walked tied drafts "
            "one at a time in file order, so its value depended on the order of the rows. "
            "The table recomputes average precision from the same per-draft rows with tied scores processed together, "
            "as `sklearn.metrics.average_precision_score` does, on the audience-gated score that the operating points use "
            "(I10 and I14 removed for an internal audience, the over-caution rule at 1.0). "
            "No model was called. From corpus v1.2, `eval screen` reports the gated tie-aware value as `auprc`, the number of "
            "distinct scores, and the file-order value under `auprc_file_order_deprecated`."
        ),
        "",
        "| Run | Drafts | Tie-aware, gated | Tie-aware, ungated | File order (v1.1, deprecated) | Distinct gated scores |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
        (
            "The distinct-score count includes 0.0 for a draft with no flag. "
            f"`docs/metrics/auprc-tieaware-{a['version']}.json` holds these values with per-category average precision "
            "and per-category recall at the 0.5 threshold. Produced by "
            f"`python3 -m socareguard.eval auprc --version {a['version']}`."
        ),
        "",
    ]


def _corpus_v12_section(sc: dict | None = None, po: dict | None = None) -> list[str]:
    """The compliant external drafts of corpus v1.2 (WSDM-N2, round 4), when they exist."""
    counts: dict[str, dict[str, int]] = {}
    for f in sorted(Path("corpus/drafts").glob("*-external-v1.2.jsonl")):
        pack = f.name.removesuffix("-external-v1.2.jsonl")
        for line in f.read_text().splitlines():
            if line.strip():
                task = json.loads(line)["task"]
                counts.setdefault(pack, {})[task] = counts.setdefault(pack, {}).get(task, 0) + 1
    if not counts:
        return []
    total = sum(sum(v.values()) for v in counts.values())
    per = ", ".join(
        f"{p} " + " and ".join(f"{n} {t.replace('_', ' ')}s" for t, n in sorted(v.items()))
        for p, v in counts.items()
    )
    return [
        "## Corpus v1.2: compliant drafts for an external reader",
        "",
        (
            f"All 300 compliant drafts of corpus v1.1 are internal case summaries, so the audience gate for I10 and I14 was not tested "
            f"against a compliant draft written for someone outside the case team. Corpus v1.2 appends {total} compliant drafts with an "
            f"external audience, each from an existing v1.1 note, written by the same drafting model and prompt ({per}). "
            "No v1.1 file was changed. The drafts are described in `corpus/drafts/README-v1.2.md`, and the run is recorded in `configs/corpus-v1.2.yaml`. "
            "With `python3 -m socareguard.eval screen --corpus v1.2`, the screen reports the false-positive rate on the compliant drafts with and without "
            "the gate, for internal and external drafts separately."
        ),
        "",
        *_gate_table(sc, po),
    ]


def _gate_table(sc: dict | None, po: dict | None) -> list[str]:
    """False-positive rate on the compliant drafts of corpus v1.2, with and without the audience
    gate, for internal and external drafts, for each screen run on that corpus."""
    runs = [
        (name, d)
        for name, d in (("Clause-grounded judge", sc), ("Prompt-only judge", po))
        if d and d.get("corpus") == "v1.2" and d["binary"].get("compliant_by_audience")
    ]
    if not runs:
        return []
    L = [
        "| Run | Internal compliant, gated | Internal compliant, ungated | External compliant, gated | External compliant, ungated | All compliant, gated / ungated |",
        "|---|---|---|---|---|---|",
    ]
    for name, d in runs:
        b = d["binary"]
        i, e = (
            b["compliant_by_audience"].get("internal", {}),
            b["compliant_by_audience"].get("external", {}),
        )
        L.append(
            f"| {name} | {i.get('fpr_gated', 0):.3f} (n={i.get('compliant_drafts', 0)}) | {i.get('fpr_ungated', 0):.3f} | "
            f"{e.get('fpr_gated', 0):.3f} (n={e.get('compliant_drafts', 0)}) | {e.get('fpr_ungated', 0):.3f} | "
            f"{b['fpr']:.3f} / {b['ungated']['fpr']:.3f} |"
        )
    L += [
        "",
        (
            "The gate removes I10 and I14 only when the draft is written for the case team, so on an external draft the gated and "
            "ungated rates are equal by construction, and the gate can lower the false-positive rate only on internal drafts. "
            "The external rate measures how often the judge raises a flag on a compliant letter or referral."
        ),
        "",
        *_external_flags(runs),
        (
            "Rescored from the same rows with no model call, the numbers on the 600 drafts of v1.1 alone "
            "(`python3 -m socareguard.eval rescore --tag v1.2` and `--tag v1.2-prompt-only`, written to "
            "`screen-v1.2-v1.1-drafts.json` and `screen-v1.2-prompt-only-v1.1-drafts.json`), are the rows headed "
            '"600 v1.1 drafts" of the comparison table below and compare like for like with v1.1.'
        ),
        "",
    ]
    return L


def _external_flags(runs: list[tuple[str, dict]]) -> list[str]:
    """The categories raised at the 0.5 threshold on the compliant external drafts, per run."""
    from collections import Counter

    from socareguard.eval.run_screen import gated_flags

    out = []
    for name, d in runs:
        p = OUT / f"screen-{d['tag']}-rows.jsonl"
        if not p.exists():
            continue
        rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        ext = [r for r in rows if r.get("audience") == "external" and r["label"] == "NONE"]
        c = Counter(k for r in ext for k, v in gated_flags(r).items() if v >= 0.5)
        flagged = sum(1 for r in ext if any(v >= 0.5 for v in gated_flags(r).values()))
        by_task = Counter(r["task"] for r in ext)
        hit = Counter(r["task"] for r in ext if any(v >= 0.5 for v in gated_flags(r).values()))
        out.append(
            f"{name}: {flagged} of {len(ext)} compliant external drafts flagged ("
            + ", ".join(
                f"{t.replace('_', ' ')}s {hit[t]} of {n}" for t, n in sorted(by_task.items())
            )
            + "). Flags raised: "
            + ", ".join(f"{k} {v}" for k, v in c.most_common())
            + "."
        )
    return out + ([""] if out else [])


def render(version: str = CURRENT) -> str:
    res = _results(version)
    full, ng, sg, rt, ut, sc, scc = (res[k] for k in ("full", "ng", "sg", "rt", "ut", "sc", "scc"))
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    L = [
        "# Metrics",
        "",
        f"Generated {datetime.now(UTC).date().isoformat()} at commit `{commit}` by `python3 -m socareguard.eval report` from the JSON files in this folder.",
        f"Corpus: `corpus-{version}` (300 synthetic notes, 4,874 gold spans, namely 4,173 entity spans scored by the detection tables and 701 attribute spans scored as attribute recall"
        + (
            ", and the screen runs on the 600 labelled drafts of v1.1 and the 90 compliant external drafts that v1.2 adds"
            if version == "v1.2"
            else ""
        )
        + "). Every number below is measured on synthetic material; see `corpus/README.md`.",
        "",
        "PDPC's Advisory Guidelines on Use of Personal Data in Generative AI (section 8.3) ask a System Provider to document the rate at which",
        "personal identifiers are detected and redacted before a request leaves the premises. These tables report that rate on synthetic notes.",
        "",
    ]
    if full:
        o = full["overall"]
        L += [
            "## Outbound detection (full pipeline)",
            "",
            f"Detectors: {', '.join(full['detectors'])}. Latency per note p50 {full['latency_s']['p50']:.2f} s, p95 {full['latency_s']['p95']:.2f} s (CPU).",
            "",
            "| Category | Exact P | Exact R | Exact F1 | Relaxed P | Relaxed R | Relaxed F1 | Gold |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for cat in sorted(o["relaxed"]):
            e, r = o["exact"].get(cat, {}), o["relaxed"][cat]
            L.append(
                f"| {cat} | {e.get('precision', 0):.3f} | {e.get('recall', 0):.3f} | {e.get('f1', 0):.3f} | {r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} | {r['tp'] + r['fn']} |"
            )
        lk = _leak(o)
        L += [
            "",
            f"**Leakage rate, matched** (gold DIRECT spans with no overlapping detection of the same category): {lk['direct_missed']} of {lk['direct_gold']} = {_pct2(lk['leakage_rate'])}.",
            "Per pack: "
            + ", ".join(
                f"{p} {_pct(_leak(v)['leakage_rate'])}" for p, v in full["per_pack"].items()
            )
            + ".",
            "",
            *(
                [
                    f"**Leakage rate, covered** (gold DIRECT spans that no direct-identifier detection overlaps): {o['leakage_covered']['direct_uncovered']} of {o['leakage_covered']['direct_gold']} = {_pct2(o['leakage_covered']['leakage_rate'])}.",
                    "",
                ]
                if "leakage_covered" in o
                else []
            ),
            "**Recall by name origin** (relaxed, NAME and THIRD_PARTY_NAME): "
            + ", ".join(
                f"{k} {_pct(v['recall'])} (n={v['n']})" for k, v in o["recall_by_origin"].items()
            )
            + ".",
            "",
            "**Attribute recall** (a gold ATTRIBUTE span counts as found when any attribute detection overlaps it): "
            + ", ".join(
                f"{k} {_pct(v['recall'])} (n={v['n']})" for k, v in full["attribute_recall"].items()
            )
            + ".",
            "",
        ]
    if full and ng and sg:
        L += [
            "## Ablation: what each layer adds",
            "",
            "| Configuration | Relaxed P | Relaxed R | Relaxed F1 | Leakage, matched | Leakage, covered | p50 latency |",
            "|---|---|---|---|---|---|---|",
        ]
        for tag, d in (
            ("Singapore recognisers + gazetteers only", sg),
            ("+ Presidio", ng),
            ("+ GLiNER2-PII (full)", full),
        ):
            a = d["overall"]["relaxed"]["ALL"]
            cov = d["overall"].get("leakage_covered")
            L.append(
                f"| {tag} | {a['precision']:.3f} | {a['recall']:.3f} | {a['f1']:.3f} | {_pct(_leak(d['overall'])['leakage_rate'])} | {_pct(cov['leakage_rate']) if cov else 'n/a'} | {d['latency_s']['p50']:.3f} s |"
            )
        sg_name = sg["overall"]["relaxed"].get("NAME", {}).get("recall")
        L += [
            "",
            "The deterministic layer alone catches every NRIC, phone number and case reference at near-perfect precision, whereas among names it catches only titled client names"
            + (f" (NAME recall {sg_name:.3f})." if sg_name is not None else "."),
            "Presidio adds most names, and GLiNER2-PII reduces the remaining name and address gap at the cost of latency.",
            "",
        ]
    if rt:
        L += [
            "## Round trip (sanitise, then restore, no model in the loop)",
            "",
            f"| Consistency (one outbound form per original) | {_pct(rt['consistency_rate'])} |",
            "|---|---|",
            f"| Injectivity (no two entities share an outbound form) | {_pct(rt['injectivity_rate'])} |",
            f"| Surrogate fidelity (every substituted span restored verbatim, none left) | {_pct(rt.get('surrogate_fidelity_rate'))} |",
            f"| Exact text fidelity (whole note identical after restore) | {_pct(rt['fidelity_exact_rate'])} |",
            f"| Gold DIRECT strings still present in the outbound text | {_pct2(rt['direct_leakage_rate'])} ({rt['direct_gold_leaked']} of {rt['direct_gold_total']}) |",
            f"| Gold ATTRIBUTE spans sent verbatim (not generalised) | {_pct(rt['attribute_verbatim_rate'])} ({rt['attr_gold_leaked_verbatim']} of {rt['attr_gold_total']}) |",
            f"| Spans substituted / generalised | {rt['surrogate_spans']} / {rt['generalised_spans']} |",
            f"| Latency p50 / p95 | {rt['latency_s']['p50']:.2f} s / {rt['latency_s']['p95']:.2f} s |",
            "",
            "Exact text fidelity is low by design: generalisation is one-way, so a note that carried a diagnosis or a",
            "school name comes back with the generalised phrase unless the model reproduced it exactly. Surrogate fidelity",
            "is the measure that matters for re-identification.",
            "",
        ]
    if ut:
        L += [
            "## Utility retention per provider",
            "",
            f"{ut['notes']} notes (10 per pack). For each provider, a case summary drafted from the raw note (never run in production) is compared",
            "with the summary drafted through the guard and restored. Both providers judge every pair on a 1 to 5 scale, blind to condition,",
            "so each provider's drafts are scored by itself and by the other model. Retention is the share of pairs rated 4 or 5.",
            "",
            "| Provider | Judge | n | Mean score | Retention | Score histogram 1..5 | Per pack mean |",
            "|---|---|---|---|---|---|---|",
        ]
        for m, v in ut["providers"].items():
            for j, jv in v["by_judge"].items():
                hist = "/".join(str(jv["score_hist"].get(str(k), 0)) for k in range(1, 6))
                L.append(
                    f"| {m} | {j} | {v['n']} | {jv['mean_score']} | {_pct(jv['retention_rate'])} | {hist} | "
                    + ", ".join(f"{p} {s}" for p, s in jv["per_pack"].items())
                    + " |"
                )
        L.append("")
        L.append(
            "Leak-check pass rate on the guarded path: "
            + ", ".join(f"{m} {_pct(v['leak_pass_rate'])}" for m, v in ut["providers"].items())
            + "."
        )
        L.append("")
    if sc:
        b = sc["binary"]
        L += [
            "## Inbound conduct screen (labelled drafts)",
            "",
            (
                f"{sc['drafts']} drafts ({sc['failure_drafts']} written under a single-failure instruction, {sc['compliant_drafts']} compliant). "
                f"Judge: `{sc['judge_model']}` at temperature 0, using the pack's SASW clause table, deterministic rules for over-caution, and "
                "disclosure categories gated on an external audience in the instruction. Labels are generation-intent labels, so these are"
            ),
            "behaviour on scripted material, not validated accuracy. F1, AUPRC and FPR are reported together, as for safety classifiers.",
            "",
            "| Scope | Precision | Recall | F1 | FPR | AUPRC |",
            "|---|---|---|---|---|---|",
            f"| Any conduct flag vs compliant | {b['precision']:.3f} | {b['recall']:.3f} | {b['f1']:.3f} | {b['fpr']:.3f} | {b['auprc']:.3f} |",
        ]
        for lab, v in sc["per_label"].items():
            L.append(
                f"| {lab} {v['name'][:48]} | {v['precision']:.3f} | {v['recall']:.3f} | {v['f1']:.3f} | {v['fpr']:.3f} | {v['auprc']:.3f} |"
            )
        L += [
            "",
            f"Intended-label recall (the instructed failure is among the flags raised): {_pct(sc['intended_label_recall'])}.",
            *(
                [
                    "False-positive rate on the compliant drafts, with the audience gate and without it: "
                    + ", ".join(
                        f"{aud} drafts ({v['compliant_drafts']}) {v['fpr_gated']:.3f} and {v['fpr_ungated']:.3f}"
                        for aud, v in b["compliant_by_audience"].items()
                    )
                    + "."
                ]
                if b.get("compliant_by_audience")
                else []
            ),
            (
                "Operating points by judge-confidence threshold (any flag vs compliant): "
                + "; ".join(
                    f"t={t}: P {v['precision']:.2f} / R {v['recall']:.2f} / F1 {v['f1']:.2f} / FPR {v['fpr']:.2f}"
                    for t, v in sc.get("threshold_sweep", {}).items()
                )
                + "."
            )
            if sc.get("threshold_sweep")
            else "",
            "",
        ]
        dist = _confidence_distribution(version)
        if dist:
            L.append(dist)
            L.append("")
        bl = sc["baseline"]
        fb = bl["failure_drafts_flagged_by"]
        L += [
            f"**Generic harm classifier on the same drafts** ({bl['name']}): precision {bl['precision']:.3f}, recall {bl['recall']:.3f}, F1 {bl['f1']:.3f}, FPR {bl['fpr']:.3f}.",
            f"Of the failure drafts, {fb['screener_only']} were flagged by the conduct screen only, {fb['both']} by both, {fb['baseline_only']} by the harm classifier only, {fb['neither']} by neither.",
            "This is the H1 finding: professional-conduct failures are largely invisible to a harm taxonomy.",
            "",
            "Per pack (any flag vs compliant): "
            + ", ".join(
                f"{p} F1 {v['f1']:.3f} / FPR {v['fpr']:.3f}" for p, v in sc["per_pack"].items()
            )
            + ".",
            "",
        ]
        if scc:
            c = scc["binary"]
            L += [
                f"**Cross-provider check** (`{scc['judge_model']}`, {scc['drafts']} drafts): any-flag precision {c['precision']:.3f}, recall {c['recall']:.3f}, F1 {c['f1']:.3f}, FPR {c['fpr']:.3f}; intended-label recall {_pct(scc['intended_label_recall'])}.",
                "The drafts were generated by gpt-4.1-mini and the runtime judge is gpt-4.1, so this second judge from another provider guards against same-family leniency.",
                "Per-category recall of the second judge at the 0.5 threshold: "
                + ", ".join(
                    f"{lab} {v['tp']} of {v['tp'] + v['fn']}" for lab, v in scc["per_label"].items()
                )
                + ".",
                "",
            ]
    po = _load(f"screen-{version}-prompt-only.json")
    if sc and po:
        L += _prompt_only_section(sc, po)
    cost_file = f"cost-{version}.json"
    cost = _load(cost_file)
    if cost is None:
        cost_file = "cost-v1.1.json"
        cost = _load(cost_file)
    if cost:
        pr, dr, jd = cost["prices"], cost["drafting"], cost["judge"]
        L += [
            "## Cost",
            "",
            (
                f"OpenAI list prices on {pr['date']} (standard tier, USD per million tokens, {pr['source'].split(' ')[0]}): "
                f"gpt-4.1-mini {pr['openai/gpt-4.1-mini']['input']:.2f} input / {pr['openai/gpt-4.1-mini']['output']:.2f} output; "
                f"gpt-4.1 {pr['openai/gpt-4.1']['input']:.2f} / {pr['openai/gpt-4.1']['output']:.2f}; omni-moderation free."
            ),
            "",
            "| Call | Model | Input tokens | Output tokens | USD per call |",
            "|---|---|---|---|---|",
            f"| Drafting | `{dr['model']}` | {dr['input_tokens_mean']} | {dr['output_tokens_mean']} | {dr['usd']:.4f} |",
            f"| Conduct judge | `{jd['model']}` | {jd['input_tokens_mean']} ({jd['input_tokens_range'][0]} to {jd['input_tokens_range'][1]}) | {jd['output_tokens_est']} (estimated) | {jd['usd']:.4f} |",
            f"| Harm-classifier baseline | `{cost['moderation']['model']}` | | | 0 |",
            f"| Per draft | | | | {cost['per_draft_usd']:.4f} |",
            "",
            f"That is approximately USD {cost['per_1000_drafts_usd']:.2f} per 1,000 drafts. A regeneration repeats the drafting and judge calls.",
            f"Drafting tokens are the means of the `usage` field over {dr['source'].split(' live')[0]} live (not replayed) request rows in the ledger of the review-round dev server of 2026-09-27. The reviewers' notes were short, and the four Use Case payloads count 76 to 276 tokens.",
            "The judge's usage is not recorded. Its input is counted by building the judge prompt for the four recorded Use Case scenarios and tokenising it with o200k_base,",
            "and its output is estimated from the flags per request in the same ledger and the size of the judge flags in saved completion responses.",
            "The judge prompt carries the pack's clause table, so the judge accounts for most of the cost. "
            + (
                f"`docs/metrics/{cost_file}` holds these figures."
                if cost_file == f"cost-{version}.json"
                else (
                    f"`docs/metrics/{cost_file}` holds these figures; the cost was measured at "
                    f"v1.1 and has not been re-run on {version}."
                )
            ),
            "",
        ]
    variants = _load(f"nric-variants-{version}.json") or _load("nric-variants.json")
    if variants:
        L += _variants_section(variants)
    tie = _load(f"auprc-tieaware-{version}.json") or _load("auprc-tieaware-v1.1.json")
    if tie:
        L += _auprc_section(tie)
    L += _corpus_v12_section(sc, po)
    L += [
        "## Reading these numbers",
        "",
        "- Gold spans are exact character offsets produced by injection, so exact-match scores are strict; relaxed (overlap) scores are the ones comparable to the de-identification literature.",
        "- Cohen's kappa is not reported for spans; the corpus has no second annotator and span kappa is the wrong instrument (Deleger et al., 2012).",
        "- Matched leakage counts a gold DIRECT span as missed when no detection of the same category overlaps it, one detection per gold span; it is the complement of direct-identifier recall and the measure reported for corpus v1.",
        "- Covered leakage counts a gold DIRECT span as leaked only when no detection of any direct-identifier category overlaps it, because such a detection is substituted whatever its label; it is the detector's share of what reaches the provider unmasked. The round-trip count of gold strings in the outbound text also reflects the sanitiser's own choices.",
        "- Dates of contact are not annotated in corpus v1 and are not scored.",
        "",
    ]
    if version != "v1" and all(_results("v1").values()):
        earlier = [
            v for v in FILES if v != version and list(FILES).index(v) < list(FILES).index(version)
        ]
        cols = {v: dict(_headline(_results(v), v)) for v in earlier}
        new = _headline(res, version)
        keys = [k for k, _ in new] + [k for v in earlier for k in cols[v] if k not in dict(new)]
        keys = list(dict.fromkeys(keys))
        newd = dict(new)
        L += [
            f"## Corpus {', '.join(earlier)} and {version}",
            "",
            "The v1 column is the result set of the first paper draft (code of commit `4868da4` for detection and round trip, `36a3ca9` for the screen and utility, corpus v1).",
            "The v1.1 column is the result set tagged `results-v1.1` (commit `b0a38ac`, corpus v1.1). Its tie-aware average precision is recomputed from the saved rows. The paper reports the v1.2 column.",
            (
                f"The {version} column is this document's result set (tag `results-{version}`). The screen rows of v1.2 are on 690 drafts, the 600 of v1.1 and 90 compliant external drafts, "
                "whereas the second judge runs on the same 180-draft subset as in v1.1. A row without an earlier value is a new measure."
            ),
            "On the 90 external drafts the clause-grounded judge flags 76 (I10 42, I14 30, I2 7). A reading of every flag against the pack clauses found the 30 I14 flags to be the youth pack's rule that escalates any external document identifying a protected young person. Of the 42 I10 flags, 14 are drafter over-disclosure (a diagnosis named to an employer who needed only a work adjustment), 9 are false positives and 18 are undecidable because the referral instruction recorded no consent. The compliant label is therefore unreliable for external drafts. The paper reports the 600 labelled drafts in its table and states this result in its text.",
            "",
            f"| Measure | {' | '.join(earlier)} | {version} |",
            "|---|" + "---|" * len(earlier) + "---|",
            *(
                f"| {k} | {' | '.join(cols[v].get(k, 'n/a') for v in earlier)} | {newd.get(k, 'n/a')} |"
                for k in keys
            ),
            "",
            "Matched leakage is higher than covered leakage mainly because matching is one-to-one: when one detection spans two gold names",
            "(a full name and the short form beside it), the second gold span counts as missed although both are substituted.",
            "Covered leakage can in turn exceed the round-trip count, because a name detected under a quasi-identifier label (an employer, say)",
            "is generalised by the sanitiser and does not reach the provider either.",
            "",
        ]
    return "\n".join(L)


def main() -> None:
    Path("docs/metrics.md").write_text(render())
    print("wrote docs/metrics.md")


if __name__ == "__main__":
    main()
