"""The supervisor summary: the ledger chain check, the drafts waiting for release, and one period
of supervisor actions with their counts.

``GET /supervisor`` renders it and ``GET /v1/supervisor/summary`` returns it as JSON. It reads the
ledger and the clear columns of the session index only, so it never decrypts a draft, and the
rows it lists carry no note or reply text (reasons are already refused when they hold an
identifier).
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from socareguard.ledger import ACTION_KINDS, Ledger, action_kind
from socareguard.taxonomy import BY_ID

DEFAULT_DAYS = 7
DEFAULT_LIMIT = 200
KIND_WORDS = {
    "escalation": "Escalated",
    "withheld_released": "Released",
    "override": "Kept with a reason",
    "rewrite_accepted": "Rewrite used",
    "review_opened": "Review opened",
}
KIND_SINGULAR = {
    "escalation": "escalation",
    "withheld_released": "release",
    "override": "passage kept with a reason",
    "rewrite_accepted": "rewrite used",
    "review_opened": "review opened",
}
KIND_PLURAL = {
    "escalation": "escalations",
    "withheld_released": "releases",
    "override": "passages kept with a reason",
    "rewrite_accepted": "rewrites used",
    "review_opened": "reviews opened",
}
_SUFFIX = re.compile(r"\s*\(self-asserted[^)]*\)\s*$")


def base_actor(actor: str | None) -> str:
    """The staff id without the ledger's "(self-asserted ...)" suffix."""
    return _SUFFIX.sub("", actor or "unattributed")


def attested(row: dict[str, Any]) -> bool:
    """Whether the row's actor was checked with a key. A request row has no ``actor_attested``
    field and marks an unchecked actor with a "(self-asserted)" suffix instead."""
    if "actor_attested" in row:
        return bool(row["actor_attested"])
    return "(self-asserted" not in (row.get("actor") or "")


def actor_label(row: dict[str, Any]) -> str:
    return (
        f"{base_actor(row.get('actor'))}, {'checked by a person' if attested(row) else 'typed in'}"
    )


def utc(ts: float | None) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d %H:%M UTC")


def day(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


def parse_when(value: str | None, end: bool = False) -> float | None:
    """A time filter: ``all``, a date (YYYY-MM-DD, UTC; the end of that day when ``end``), an
    ISO date and time, or seconds since the epoch. None when empty. ValueError otherwise."""
    value = (value or "").strip()
    if not value:
        return None
    if value == "all":
        return 0.0
    try:
        return float(value)
    except ValueError:
        pass
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        d = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()
        return d + 86400 - 0.001 if end else d
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


def chain_block(ledger: Ledger) -> dict[str, Any]:
    r = ledger.report()
    gaps = [x for x in (r["first_bad_row"], r["first_seq_gap"]) if x is not None]
    logged = ledger.last_logged
    if r["ok"]:
        message = (
            f"The record has not been altered since the last check: {r['rows']} "
            f"row{'' if r['rows'] == 1 else 's'} in the record, no gaps."
        )
    elif r["first_bad_row"] is not None:
        message = f"The record was altered at row {r['first_bad_row']} of {r['rows']}."
    else:
        message = f"The row numbers break at row {r['first_seq_gap']} of {r['rows']}."
    return {
        "ok": r["ok"],
        "rows": r["rows"],
        "head_sha256": r["head_sha256"],
        "first_bad_row": r["first_bad_row"],
        "first_seq_gap": r["first_seq_gap"],
        "first_gap": min(gaps) if gaps else None,
        "last_logged": logged,
        "logged_head_matches": (
            None
            if logged is None
            else logged["head_sha256"] == r["head_sha256"] and logged["rows"] == r["rows"]
        ),
        "message": message,
    }


def _categories(labels: list[str] | None) -> list[dict[str, str]]:
    out = []
    for label in labels or []:
        cat = BY_ID.get(label)
        out.append({"label": label, "clause": cat.clause if cat else ""})
    return out


def _action(row: dict[str, Any], kind: str, pack: str | None) -> dict[str, Any]:
    request_row = row.get("request_row_sha256") or (
        row.get("row_sha256") if kind == "escalation" else None
    )
    decision = KIND_WORDS[kind]
    if kind == "escalation" and row.get("withheld"):
        decision = "Escalated, draft withheld"
    return {
        "ts": row.get("ts"),
        "time": utc(row.get("ts")),
        "session": row.get("session"),
        "pack": pack,
        "kind": kind,
        "decision": decision,
        "actor": base_actor(row.get("actor")),
        "actor_attested": attested(row),
        "actor_label": actor_label(row),
        "categories": _categories(row.get("flags")),
        "reason": row.get("override_reason") or "",
        "request_row_sha256": request_row,
        "row_sha256": row.get("row_sha256"),
    }


def build_summary(
    ledger: Ledger,
    sessions: Any,
    *,
    since: float | None = None,
    until: float | None = None,
    pack: str | None = None,
    category: str | None = None,
    actor: str | None = None,
    kind: str | None = None,
    limit: int = DEFAULT_LIMIT,
    now: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now is None else now
    if since is None:
        since = now - DEFAULT_DAYS * 86400
    if kind and kind not in ACTION_KINDS:
        raise ValueError(f"kind must be one of {', '.join(ACTION_KINDS)}")

    # The drafts waiting for release: a withheld session with no release row written after its
    # latest result. Releases cannot predate a session, so the scan starts at the oldest one.
    withheld = sessions.withheld_sessions()
    scan_from = min([w["created"] for w in withheld] + [since]) - 1
    scanned = ledger.rows_since(scan_from)
    pack_of: dict[str, str] = {}
    request_of: dict[str, dict[str, Any]] = {}
    for row in scanned:
        s = row.get("session")
        if s and row.get("pack"):
            pack_of[s] = row["pack"]
        if s and row.get("decision") == "escalate":
            request_of[s] = row
    queue = []
    for w in withheld:
        released = any(
            r.get("decision") == "withheld_released"
            and r.get("session") == w["session"]
            and r.get("ts", 0) >= w["updated"] - 1
            for r in scanned
        )
        if released:
            continue
        if pack and w["pack"] != pack:
            continue
        if category and category not in w["flags"]:
            continue
        req = request_of.get(w["session"], {})
        queue.append(
            {
                "session": w["session"],
                "pack": w["pack"],
                "ts": w["updated"],
                "time": utc(w["updated"]),
                "categories": _categories(w["flags"]),
                "practitioner": base_actor(req.get("actor")) if req else "not in the ledger",
                "practitioner_label": actor_label(req) if req else "not in the ledger",
                "request_row_sha256": req.get("row_sha256"),
                "reviews_open": w["reviews_open"],
            }
        )

    # One period of actions.
    in_period = [
        r for r in scanned if r.get("ts", 0) >= since and (until is None or r.get("ts", 0) <= until)
    ]
    actions_all = []
    for row in in_period:
        k = action_kind(row)
        if k is None:
            continue
        p = (
            row.get("pack")
            or pack_of.get(row.get("session") or "")
            or (sessions.pack(row["session"]) if row.get("session") else None)
        )
        actions_all.append(_action(row, k, p))
    options = {
        "pack": sorted({a["pack"] for a in actions_all if a["pack"]} | {q["pack"] for q in queue}),
        "category": sorted({c["label"] for a in actions_all for c in a["categories"]}),
        "actor": sorted({a["actor"] for a in actions_all}),
        "kind": list(ACTION_KINDS),
    }
    actions = [
        a
        for a in actions_all
        if (not pack or a["pack"] == pack)
        and (not category or any(c["label"] == category for c in a["categories"]))
        and (not actor or a["actor"] == actor)
        and (not kind or a["kind"] == kind)
    ]
    counts = {k: sum(1 for a in actions if a["kind"] == k) for k in ACTION_KINDS}
    actions.reverse()  # newest first
    return {
        "chain": chain_block(ledger),
        "queue": queue,
        "actions": actions[: max(limit, 0)],
        "total": len(actions),
        "counts": counts,
        "filters": {
            "applied": {
                "since": since,
                "until": until,
                "pack": pack,
                "category": category,
                "actor": actor,
                "kind": kind,
                "limit": limit,
            },
            "period": {
                "since": utc(since) if since else "the first row",
                "until": utc(until) if until else "now",
            },
            "options": options,
        },
    }


FILTER_NAMES = ("pack", "category", "actor", "kind", "since", "until")
GROUP_LABELS = {
    "pack": "Policy pack",
    "category": "Category",
    "actor": "Actor",
    "kind": "Kind",
    "since": "Period",
}


def _url(params: dict[str, str]) -> str:
    kept = {k: v for k, v in params.items() if v}
    return "/supervisor" + ("?" + urlencode(kept) if kept else "")


def chip_groups(raw: dict[str, str], options: dict[str, list[str]], now: float) -> list[dict]:
    """The filter chips of the supervisor page. ``raw`` holds the query as typed; each chip is a
    link that changes one filter and keeps the others."""
    raw = {k: raw.get(k, "") for k in FILTER_NAMES}
    groups = []
    for name in ("pack", "category", "actor", "kind"):
        values = list(options.get(name) or [])
        if raw[name] and raw[name] not in values:
            values.append(raw[name])
        chips = [
            {"label": "All", "value": "", "url": _url({**raw, name: ""}), "active": not raw[name]}
        ]
        for v in values:
            label = KIND_WORDS.get(v, v) if name == "kind" else v
            if name == "category" and v in BY_ID:
                label = f"{v} {BY_ID[v].plain or BY_ID[v].name}"
            chips.append(
                {
                    "label": label,
                    "value": v,
                    "url": _url({**raw, name: v}),
                    "active": raw[name] == v,
                }
            )
        groups.append({"name": name, "label": GROUP_LABELS[name], "chips": chips})
    periods = [
        ("Last 7 days", ""),
        ("Today", day(now)),
        ("Last 30 days", day(now - 30 * 86400)),
        ("All time", "all"),
    ]
    groups.append(
        {
            "name": "since",
            "label": GROUP_LABELS["since"],
            "chips": [
                {
                    "label": label,
                    "value": v,
                    "url": _url({**raw, "since": v, "until": ""}),
                    "active": raw["since"] == v and not raw["until"],
                }
                for label, v in periods
            ],
        }
    )
    return groups
