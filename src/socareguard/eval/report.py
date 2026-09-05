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


def render() -> str:
    full, ng, sg = (
        _load("detect-full.json"),
        _load("detect-no-gliner.json"),
        _load("detect-sg-only.json"),
    )
    rt, ut = _load("roundtrip-v1.json"), _load("utility-v1.json")
    sc, scc = _load("screen-v1.json"), _load("screen-v1-claude.json")
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    L = [
        "# Metrics",
        "",
        f"Generated {datetime.now(UTC).date().isoformat()} at commit `{commit}` by `python3 -m socareguard.eval report` from the JSON files in this folder.",
        "Corpus: `corpus-v1` (300 synthetic notes, 4,874 gold spans). Every number below is measured on synthetic material; see `corpus/README.md`.",
        "",
        "These tables are the compliance artefact that PDPC's Advisory Guidelines on Use of Personal Data in Generative AI (section 8.3)",
        "ask a System Provider to document: the rate at which personal identifiers are detected and redacted before a request leaves the premises.",
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
        lk = o["leakage"]
        L += [
            "",
            f"**Leakage rate** (gold DIRECT spans with no overlapping detection): {lk['direct_missed']} of {lk['direct_gold']} = {_pct(lk['leakage_rate'])}.",
            "Per pack: "
            + ", ".join(
                f"{p} {_pct(v['leakage']['leakage_rate'])}" for p, v in full["per_pack"].items()
            )
            + ".",
            "",
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
            "| Configuration | Relaxed P | Relaxed R | Relaxed F1 | Leakage | p50 latency |",
            "|---|---|---|---|---|---|",
        ]
        for tag, d in (
            ("Singapore recognisers + gazetteers only", sg),
            ("+ Presidio", ng),
            ("+ GLiNER2-PII (full)", full),
        ):
            a = d["overall"]["relaxed"]["ALL"]
            L.append(
                f"| {tag} | {a['precision']:.3f} | {a['recall']:.3f} | {a['f1']:.3f} | {_pct(d['overall']['leakage']['leakage_rate'])} | {d['latency_s']['p50']:.3f} s |"
            )
        L += [
            "",
            "The deterministic layer alone catches every NRIC, phone number and case reference at near-perfect precision but no names;",
            "Presidio adds most names; GLiNER2-PII closes the remaining name and address gap at the cost of latency.",
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
            f"| Gold DIRECT strings still present in the outbound text | {_pct(rt['direct_leakage_rate'])} ({rt['direct_gold_leaked']} of {rt['direct_gold_total']}) |",
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
            "with the summary drafted through the guard and restored; both providers judge every pair on a 1 to 5 scale, blind to condition,",
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
                f"Judge: `{sc['judge_model']}` at temperature 0 with the pack's SASW clause table; deterministic rules for over-caution; "
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
                "",
            ]
    L += [
        "## Reading these numbers",
        "",
        "- Gold spans are exact character offsets produced by injection, so exact-match scores are strict; relaxed (overlap) scores are the ones comparable to the de-identification literature.",
        "- Cohen's kappa is not reported for spans; the corpus has no second annotator and span kappa is the wrong instrument (Deleger et al., 2012).",
        "- Leakage counts a miss whenever a gold DIRECT span has no overlapping detection, whatever the reason.",
        "- Dates of contact are not annotated in corpus v1 and are not scored.",
        "",
    ]
    return "\n".join(L)


def main() -> None:
    Path("docs/metrics.md").write_text(render())
    print("wrote docs/metrics.md")


if __name__ == "__main__":
    main()
