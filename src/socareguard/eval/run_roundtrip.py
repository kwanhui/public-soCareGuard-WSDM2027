"""Round-trip metrics without a model: sanitise each note, restore it, compare.

Reports surrogate consistency (one outbound form per original within a note), injectivity
(no two originals share an outbound form), round-trip fidelity (restored text equals the
original for surrogate spans, while generalised spans are one-way by design and are reported
separately), gold DIRECT leakage of the outbound text, and latency.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from socareguard.corpus.schema import Note, SpanType
from socareguard.inbound.restore import restore
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack

OUT = Path("docs/metrics")


def _base(text: str) -> str:
    """A form without its possessive, so that "Wei Ming's" and "Wei Ming" count as one original."""
    return re.sub(r"['\u2019]s$", "", text)


def _same_entity(originals: set[str]) -> bool:
    lows = sorted((o.lower() for o in originals), key=len)
    return all(a in b or b in a or a.split()[-1] == b.split()[-1] for a in lows for b in lows)


def run(notes: list[Note], tag: str, vault_path: Path | None = None) -> dict[str, Any]:
    vault = Vault(vault_path or Path("vault/eval-roundtrip.sqlite"))
    stats = {
        "notes": 0,
        "consistent": 0,
        "injective": 0,
        "fidelity_exact": 0,
        "surrogate_fidelity": 0,
        "direct_gold_total": 0,
        "direct_gold_leaked": 0,
        "attr_gold_total": 0,
        "attr_gold_leaked_verbatim": 0,
        "generalised_spans": 0,
        "surrogate_spans": 0,
    }
    lat = []
    for n in notes:
        pack = load_pack(n.pack)
        san = Sanitiser(vault, pack)
        t0 = time.perf_counter()
        s = san.sanitise(n.text, session=f"rt-{n.id}", seed=n.seed)
        lat.append(time.perf_counter() - t0)
        stats["notes"] += 1
        by_orig: dict[tuple[str, str], set[str]] = {}
        by_out: dict[str, set[str]] = {}
        for h, new, kind in s.replacements:
            by_orig.setdefault((h.category, _base(h.text)), set()).add(_base(new))
            if kind == "surrogate":
                by_out.setdefault(new, set()).add(h.text)
                stats["surrogate_spans"] += 1
            elif kind == "generalised":
                stats["generalised_spans"] += 1
        stats["consistent"] += int(all(len(v) == 1 for v in by_orig.values()))
        # Two originals may share an outbound form only when they are forms of the same entity
        # (a full name and its short form); anything else is an injectivity failure.
        stats["injective"] += int(all(_same_entity(v) for v in by_out.values()))
        r = restore(s.text, vault, f"rt-{n.id}", restore_generalised=True)
        stats["fidelity_exact"] += int(r.text == n.text)
        # Surrogate spans must all come back verbatim and no surrogate may remain: the one-way
        # generalised spans are excluded from this measure by design.
        surr = [(h, new) for h, new, kind in s.replacements if kind == "surrogate"]
        stats["surrogate_fidelity"] += int(
            all(h.text in r.text for h, _ in surr)
            and not any(new in r.text for _, new in surr if new not in n.text)
        )
        for g in n.spans:
            if g.type is SpanType.DIRECT:
                stats["direct_gold_total"] += 1
                if len(g.text) > 2 and g.text in s.text:
                    stats["direct_gold_leaked"] += 1
            elif g.type is SpanType.ATTRIBUTE:
                stats["attr_gold_total"] += 1
                if g.text in s.text:
                    stats["attr_gold_leaked_verbatim"] += 1
        vault.forget(f"rt-{n.id}")
    lat.sort()
    n_ = max(stats["notes"], 1)
    res = {
        "tag": tag,
        **stats,
        "consistency_rate": round(stats["consistent"] / n_, 4),
        "injectivity_rate": round(stats["injective"] / n_, 4),
        "fidelity_exact_rate": round(stats["fidelity_exact"] / n_, 4),
        "surrogate_fidelity_rate": round(stats["surrogate_fidelity"] / n_, 4),
        "direct_leakage_rate": round(
            stats["direct_gold_leaked"] / max(stats["direct_gold_total"], 1), 4
        ),
        "attribute_verbatim_rate": round(
            stats["attr_gold_leaked_verbatim"] / max(stats["attr_gold_total"], 1), 4
        ),
        "latency_s": {
            "p50": round(lat[len(lat) // 2], 3),
            "p95": round(lat[int(len(lat) * 0.95) - 1], 3),
        }
        if lat
        else {},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"roundtrip-{tag}.json").write_text(json.dumps(res, indent=2))
    return res
