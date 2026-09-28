"""Score the detection pipeline against corpus gold spans.

python3 -m socareguard.eval detect [--packs ...] [--limit N] [--no-gliner] [--no-presidio]
Writes docs/metrics/detect-<tag>.json and .csv. Entity categories are scored exact and
relaxed, and attributes relaxed only (any overlap with a gold ATTRIBUTE span of the same key).
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from socareguard.corpus.schema import Note, SpanType
from socareguard.detect.pipeline import detect
from socareguard.eval import spans as ev

OUT = Path("docs/metrics")


def attribute_recall(note: Note, attr_hits) -> dict[str, list[int]]:
    """Per key: [hits, gold]. A gold ATTRIBUTE span counts as found if any attr hit overlaps it."""
    out: dict[str, list[int]] = {}
    for g in note.spans:
        if g.type is not SpanType.ATTRIBUTE or not g.arg:
            continue
        found = any(h.start < g.end and g.start < h.end for h in attr_hits)
        rec = out.setdefault(g.arg, [0, 0])
        rec[1] += 1
        rec[0] += int(found)
    return out


def run(notes: list[Note], use_presidio: bool, use_gliner: bool, tag: str) -> dict[str, Any]:
    reports = []
    per_pack: dict[str, list[ev.Report]] = {}
    attr_tot: dict[str, list[int]] = {}
    latencies = []
    for n in notes:
        t0 = time.perf_counter()
        d = detect(n.text, use_presidio=use_presidio, use_gliner=use_gliner)
        latencies.append(time.perf_counter() - t0)
        preds = [ev.Pred(h.start, h.end, h.category, h.score) for h in d.entities]
        r = ev.score_note(n, preds)
        reports.append(r)
        per_pack.setdefault(n.pack, []).append(r)
        for k, (h, g) in attribute_recall(n, d.attributes).items():
            rec = attr_tot.setdefault(k, [0, 0])
            rec[0] += h
            rec[1] += g
    merged = ev.merge(reports).as_dict()
    lat = sorted(latencies)
    result = {
        "tag": tag,
        "notes": len(notes),
        "detectors": d.detectors if notes else [],
        "overall": merged,
        "per_pack": {p: ev.merge(rs).as_dict() for p, rs in sorted(per_pack.items())},
        "attribute_recall": {
            k: {"recall": round(h / g, 4) if g else 0.0, "n": g}
            for k, (h, g) in sorted(attr_tot.items())
        },
        "latency_s": {
            "p50": round(lat[len(lat) // 2], 4),
            "p95": round(lat[int(len(lat) * 0.95) - 1], 4),
            "mean": round(sum(lat) / len(lat), 4),
        }
        if lat
        else {},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"detect-{tag}.json").write_text(json.dumps(result, indent=2))
    with (OUT / f"detect-{tag}.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scope", "category", "mode", "tp", "fp", "fn", "precision", "recall", "f1"])
        for scope, rep in [("all", merged)] + list(result["per_pack"].items()):
            for mode in ("exact", "relaxed"):
                for cat, v in rep[mode].items():
                    w.writerow(
                        [
                            scope,
                            cat,
                            mode,
                            v["tp"],
                            v["fp"],
                            v["fn"],
                            v["precision"],
                            v["recall"],
                            v["f1"],
                        ]
                    )
        for o, v in merged["recall_by_origin"].items():
            w.writerow(["all", f"origin:{o}", "relaxed", "", "", "", "", v["recall"], ""])
        for k, v in result["attribute_recall"].items():
            w.writerow(["all", f"attr:{k}", "relaxed", "", "", "", "", v["recall"], ""])
        for name, missed in (
            ("leakage_matched", "direct_missed"),
            ("leakage_covered", "direct_uncovered"),
        ):
            lk = merged[name]
            w.writerow(["all", name, "relaxed", "", "", lk[missed], "", lk["leakage_rate"], ""])
    return result


VARIANTS = Path("tests/data/nric-variants.jsonl")
DIRECT = set(ev.DIRECT_CATEGORIES)


def run_variants(
    use_presidio: bool = True,
    use_gliner: bool = True,
    path: Path = VARIANTS,
    tag: str | None = None,
) -> dict[str, Any]:
    """Recall on the NRIC and FIN format-variant stress set: spaced, hyphenated, lower case,
    with an "NRIC:" prefix and in parentheses. The corpus writes every identifier in the canonical
    form of the identifier factory that the recogniser shares, so these variants are measured on
    their own. A variant counts as detected when an NRIC span covers it exactly (``exact``) or when
    any direct-identifier span overlaps it (``covered``, since any such span is substituted), and
    as leaked when its text survives in the sanitised text."""
    from socareguard.outbound.sanitise import Sanitiser
    from socareguard.outbound.vault import Vault
    from socareguard.policy.loader import load_pack

    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    vault = Vault(Path("vault/eval-variants.sqlite"))
    by_form: dict[str, list[int]] = {}
    per_row = []
    exact = covered = leaked = 0
    for r in rows:
        det = detect(r["text"], use_presidio=use_presidio, use_gliner=use_gliner, attributes=False)
        ex = any(
            h.category == "NRIC" and h.start == r["start"] and h.end == r["end"]
            for h in det.entities
        )
        cov = any(
            h.category in DIRECT and h.start < r["end"] and r["start"] < h.end for h in det.entities
        )
        san = Sanitiser(vault, load_pack("disability"), use_presidio, use_gliner)
        out = san.sanitise(r["text"], session=f"var-{r['id']}", seed=1).text
        vault.forget(f"var-{r['id']}")
        lk = r["variant"] in out or r["canonical"] in out
        exact, covered, leaked = exact + ex, covered + cov, leaked + lk
        f = by_form.setdefault(r["form"], [0, 0])
        f[0] += int(cov)
        f[1] += 1
        per_row.append(
            {"id": r["id"], "form": r["form"], "exact": ex, "covered": cov, "leaked": lk}
        )
    n = len(rows)
    res = {
        "file": str(path),
        "variants": n,
        "detectors": det.detectors if rows else [],
        "recall_exact": round(exact / n, 4) if n else None,
        "recall_covered": round(covered / n, 4) if n else None,
        "leaked": leaked,
        "by_form": {k: {"covered": v[0], "total": v[1]} for k, v in by_form.items()},
        "rows": per_row,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    name = f"nric-variants-{tag}.json" if tag else "nric-variants.json"
    (OUT / name).write_text(json.dumps(res, indent=2))
    return res
