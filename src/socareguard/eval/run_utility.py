"""Per-provider utility retention.

For a sample of notes and each provider: draft a case summary from the raw note (the
unsafe baseline that never runs in production) and from the pseudonymised note with
the reply restored (the guarded path). The other provider judges, blind to condition,
whether the guarded draft preserves the facts and usefulness of the unguarded one on a
1 to 5 scale. Utility retention is the share of pairs rated 4 or 5. Reported per provider
because redaction tolerance differs widely across models.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from socareguard.corpus.schema import Note
from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.proxy.core import Guard, complete

OUT = Path("docs/metrics")
TASK = "Write a concise case summary (about 120 words) followed by a next-step plan of 3 to 5 numbered actions, for the supervising social worker to review."
JUDGE = """You compare two case-summary drafts written from the same social-work case note. Draft A was written from the original note. Draft B was written from a version of the note in which identifiers were replaced by realistic substitutes and some sensitive details were generalised, and then the identifiers were restored.

Rate how well Draft B preserves the professional usefulness of Draft A for the supervising social worker: the same facts, the same risks and strengths, the same plan. Ignore differences in wording and ordering. Ignore whether names or numbers differ. Penalise only missing or wrong substance.

Scale: 5 = equivalent; 4 = minor loss that would not change practice; 3 = a noticeable omission or a generalisation that a supervisor would ask about; 2 = a material gap; 1 = unusable.

Reply with a JSON object: {"score": <1-5>, "reason": "<one sentence>"}."""


def _judge(judge_model: str, a: str, b: str) -> tuple[int, str]:
    text, _ = complete(
        judge_model,
        [
            {"role": "system", "content": JUDGE},
            {"role": "user", "content": f"Draft A:\n{a}\n\nDraft B:\n{b}"},
        ],
        temperature=0,
    )
    m = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        d = json.loads(m.group(0)) if m else {}
        return int(d.get("score", 0)), str(d.get("reason", ""))[:200]
    except Exception:  # noqa: BLE001
        return 0, text[:200]


def run(
    notes: list[Note], providers: list[str], tag: str, vault_path: Path | None = None
) -> dict[str, Any]:
    guard = Guard(
        vault=Vault(vault_path or Path("vault/eval-utility.sqlite")),
        ledger=Ledger(Path("vault/eval-utility-ledger.jsonl")),
    )
    results: dict[str, Any] = {"tag": tag, "notes": len(notes), "providers": {}}
    rows = []

    def one(note: Note, model: str) -> dict[str, Any]:
        msgs = [{"role": "user", "content": f"Case note:\n\n{note.text}\n\nTask: {TASK}"}]
        raw_draft, _ = complete(model, msgs, temperature=0)
        res = guard.run(
            msgs,
            note.pack,
            model,
            session=f"ut-{model.split('/')[1]}-{note.id}",
            seed=note.seed,
            provider_kwargs={"temperature": 0},
        )
        scores = {}
        for judge_model in providers:
            score, reason = _judge(judge_model, raw_draft, res.reply)
            scores[judge_model] = (score, reason)
        guard.vault.forget(res.session)
        leak_events = [e for e in res.events if e.kind == "leakcheck"]
        return {
            "note": note.id,
            "pack": note.pack,
            "provider": model,
            "scores": {j: sc for j, (sc, _) in scores.items()},
            "reasons": {j: rs for j, (_, rs) in scores.items()},
            "n_substituted": sum(e.n_spans for e in res.events if e.kind == "substitute"),
            "leak_passed": all(e.passed for e in leak_events),
            "leak_detail": [x.model_dump() for e in leak_events for x in e.leaks],
        }

    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(one, n, m) for m in providers for n in notes]
        for f in futs:
            rows.append(f.result())
    for m in providers:
        rs = [r for r in rows if r["provider"] == m]
        entry: dict[str, Any] = {
            "n": len(rs),
            "leak_pass_rate": round(sum(1 for r in rs if r["leak_passed"]) / len(rs), 4)
            if rs
            else None,
            "by_judge": {},
        }
        for j in providers:
            scores = [r["scores"][j] for r in rs if r["scores"].get(j, 0) > 0]
            entry["by_judge"][j] = {
                "mean_score": round(sum(scores) / len(scores), 3) if scores else None,
                "retention_rate": round(sum(1 for s in scores if s >= 4) / len(scores), 4)
                if scores
                else None,
                "score_hist": {str(k): scores.count(k) for k in range(1, 6)},
                "per_pack": {
                    p: round(
                        sum(r["scores"][j] for r in rs if r["pack"] == p)
                        / max(1, sum(1 for r in rs if r["pack"] == p)),
                        3,
                    )
                    for p in sorted({r["pack"] for r in rs})
                },
            }
        allsc = [r["scores"][j] for r in rs for j in providers if r["scores"].get(j, 0) > 0]
        entry["mean_score_all_judges"] = round(sum(allsc) / len(allsc), 3) if allsc else None
        entry["retention_rate_all_judges"] = (
            round(sum(1 for s in allsc if s >= 4) / len(allsc), 4) if allsc else None
        )
        results["providers"][m] = entry
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"utility-{tag}.json").write_text(json.dumps(results, indent=2))
    with (OUT / f"utility-{tag}.csv").open("w") as f:
        f.write("note,pack,provider,judge,score,n_substituted,leak_passed,leak_detail,reason\n")
        for r in sorted(rows, key=lambda r: (r["provider"], r["note"])):
            for j in providers:
                reason = r["reasons"].get(j, "").replace('"', "'")
                detail = "; ".join(
                    f"{x['category']}:{x['text']}" for x in r["leak_detail"]
                ).replace('"', "'")
                f.write(
                    f'{r["note"]},{r["pack"]},{r["provider"]},{j},{r["scores"].get(j, 0)},{r["n_substituted"]},{r["leak_passed"]},"{detail}","{reason}"\n'
                )
    return results
