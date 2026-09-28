"""Validate and replay scenario scripts.

``validate`` checks a script's schema and internal consistency without any model or
detector; a script without ``expect`` lines (the escalation chip's recording) is valid and
reported with a warning. ``run`` drives a pipeline object that implements ``Pipeline`` and
then evaluates the ``expect`` lines against the events it emitted. ``run --proxy`` drives the
real guard; without it, ``StoryboardPipeline`` only echoes the recorded events, so ``expect``
checks that reference detection or screening are reported as pending rather than failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Protocol

from socareguard.scenarios.events import (
    EVENT_ADAPTER,
    Expect,
    Override,
    Receive,
    ScenarioHeader,
    UserTurn,
)
from socareguard.scenarios.events import (
    Ledger as LedgerEvent,
)

SCENARIO_DIR = Path("demo/sample-inputs/scenarios")
WARNING = "warning: "


def load(path: Path) -> list[Any]:
    events = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            events.append(EVENT_ADAPTER.validate_json(line))
        except Exception as e:
            raise ValueError(f"{path}:{i}: {e}") from e
    return events


def validate(path: Path) -> list[str]:
    problems: list[str] = []
    events = load(path)
    if not events or not isinstance(events[0], ScenarioHeader):
        return [f"{path}: first line must be a scenario header"]
    seqs = [e.seq for e in events[1:]]
    if seqs != sorted(seqs):
        problems.append("seq numbers are not monotonic")
    turns = [e for e in events if isinstance(e, UserTurn)]
    if not turns:
        problems.append("no user_turn")
    recv = [e for e in events if isinstance(e, Receive)]
    if not recv:
        problems.append("no receive fixture; replay would need a live model")
    for r in recv:
        if r.source == "recorded" and not (r.model and r.recorded_at):
            problems.append(f"seq {r.seq}: recorded receive must carry model and recorded_at")
    expects = [e for e in events if isinstance(e, Expect)]
    if not expects:
        # a recording kept for the panel's replay, with nothing to assert
        problems.append(WARNING + "no expect lines")
    kinds = {
        "detect",
        "generalise",
        "substitute",
        "send",
        "receive",
        "reidentify",
        "leakcheck",
        "screen",
        "action",
        "override",
        "ledger",
    }
    for e in expects:
        if e.event not in kinds:
            problems.append(f"seq {e.seq}: expect references unknown event {e.event}")
    return problems


class Pipeline(Protocol):
    def run(
        self, turn: UserTurn, fixture: Receive | None, overrides: list[Override] | None = None
    ) -> list[Any]: ...


class ProxyPipeline:
    """Drives the real guard. Uses the script's recorded/authored reply as the model reply unless
    ``live`` is set. Script ``override`` lines are applied through the guard after the run."""

    def __init__(
        self, pack: str, guard=None, live: bool = False, model: str = "openai/gpt-4.1-mini"
    ):
        from socareguard.proxy.core import Guard

        self.pack, self.live, self.model = pack, live, model
        self.guard = guard or Guard()

    def run(
        self, turn: UserTurn, fixture: Receive | None, overrides: list[Override] | None = None
    ) -> list[Any]:
        msgs = [{"role": "user", "content": f"{turn.instruction}\n\n{turn.note}"}]
        fixture_text = None if self.live or fixture is None else fixture.text
        res = self.guard.run(msgs, self.pack, self.model, reply_fixture=fixture_text, seed=turn.seq)
        events = list(res.events)
        seq = max(e.seq for e in events) + 1
        for o in overrides or []:
            row = self.guard.override(res.session, o.by, o.flag_labels, o.reason, self.pack)
            events.append(Override(seq=seq, by=o.by, flag_labels=o.flag_labels, reason=o.reason))
            events.append(
                LedgerEvent(
                    seq=seq + 1,
                    row_sha256=row["row_sha256"],
                    prev_sha256=row["prev_sha256"],
                    fields=row,
                )
            )
            seq += 2
        return events


class StoryboardPipeline:
    """Echoes the script's own events. Used before the proxy exists."""

    def __init__(self, events: list[Any]):
        self.events = events

    def run(
        self, turn: UserTurn, fixture: Receive | None, overrides: list[Override] | None = None
    ) -> list[Any]:
        return [e for e in self.events if not isinstance(e, (ScenarioHeader, UserTurn, Expect))]


def check(expect: Expect, emitted: list[Any]) -> tuple[str, str]:
    """Evaluate one expect line. Returns (status, detail) with status in pass/fail/pending."""
    matches = [e for e in emitted if getattr(e, "kind", None) == expect.event]
    if not matches:
        return "pending", f"no {expect.event} event emitted"
    ev = matches[-1]
    for key, want in expect.check.items():
        if key == "categories_include":
            have = {s.category for s in ev.spans}
            missing = set(want) - have
            if missing:
                return "fail", f"detect is missing {sorted(missing)}"
        elif key == "min_spans":
            if len(ev.spans) < want:
                return "fail", f"{len(ev.spans)} spans < {want}"
        elif key == "passed":
            if ev.passed is not want:
                return "fail", f"leakcheck passed={ev.passed}"
        elif key == "flags_include":
            have = {f.label for f in ev.flags}
            if not set(want) <= have:
                return "fail", f"screen flags {sorted(have)} lack {want}"
        elif key == "flags_any":
            have = {f.label for f in ev.flags}
            if not (set(want) & have):
                return "fail", f"screen flags {sorted(have)} include none of {want}"
        elif key == "flags_exclude":
            have = {f.label for f in ev.flags}
            if set(want) & have:
                return "fail", f"screen flagged {sorted(set(want) & have)}"
        elif key == "baseline_flags_empty":
            if want and ev.baseline_flags:
                return "fail", f"baseline flagged {ev.baseline_flags}"
        elif key == "decision":
            if ev.decision != want:
                return "fail", f"decision {ev.decision} != {want}"
        elif key == "decision_in":
            if ev.decision not in want:
                return "fail", f"decision {ev.decision} not in {want}"
        elif key == "reason_nonempty":
            if want and not ev.reason.strip():
                return "fail", "override reason empty"
        elif key == "outbound_excludes":
            text = ev.outbound_text or ""
            leaked = [w for w in want if w in text]
            if leaked:
                return "fail", f"outbound payload still contains {leaked}"
        elif key == "rules_min":
            if len(ev.rules) < want:
                return "fail", f"{len(ev.rules)} generalisation rules < {want}"
        elif key == "fields_include":
            missing = [k for k in want if k not in ev.fields]
            if missing:
                return "fail", f"ledger row lacks {missing}"
        else:
            return "fail", f"unknown check {key}"
    return "pass", "ok"


def run(
    path: Path, pipeline: Pipeline | None = None, mode: str = "storyboard", live: bool = False
) -> dict[str, Any]:
    events = load(path)
    header = events[0]
    turns = [e for e in events if isinstance(e, UserTurn)]
    fixtures = [e for e in events if isinstance(e, Receive)]
    if pipeline is None:
        pipeline = (
            ProxyPipeline(header.pack, live=live) if mode == "proxy" else StoryboardPipeline(events)
        )
    pipe = pipeline
    overrides = [e for e in events if isinstance(e, Override)]
    emitted: list[Any] = []
    for i, t in enumerate(turns):
        emitted += pipe.run(
            t,
            fixtures[i] if i < len(fixtures) else None,
            overrides if i == len(turns) - 1 else None,
        )
    screened = any(getattr(e, "kind", None) == "screen" for e in emitted)
    results = []
    for e in events:
        if isinstance(e, Expect):
            status, detail = check(e, emitted)
            if status == "fail" and not screened and e.event == "action":
                status, detail = (
                    "pending",
                    "the conduct screen did not run (SOCAREGUARD_SCREEN=off or no judge key): "
                    + detail,
                )
            results.append(
                {"seq": e.seq, "event": e.event, "status": status, "detail": detail, "why": e.why}
            )
    return {
        "scenario": header.id,
        "title": header.title,
        "results": results,
        "summary": {
            s: sum(1 for r in results if r["status"] == s) for s in ("pass", "fail", "pending")
        },
    }


def record(path: Path, model: str) -> dict[str, Any]:
    """Run the scenario live and replace its reply fixture with the recorded model reply."""
    from datetime import UTC, datetime

    from dotenv import load_dotenv

    load_dotenv()
    events = load(path)
    header = events[0]
    pipe = ProxyPipeline(header.pack, live=True, model=model)
    turns = [e for e in events if isinstance(e, UserTurn)]
    emitted = pipe.run(turns[0], None)
    reply = next(e for e in emitted if e.kind == "receive")
    send = next(e for e in emitted if e.kind == "send")
    out_lines = []
    for e in events:
        if isinstance(e, Receive):
            e = Receive(
                seq=e.seq,
                source="recorded",
                provider=model.split("/")[0],
                model=model,
                recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
                text=reply.text,
            )
        elif e.kind == "send":
            e = e.model_copy(
                update={
                    "provider": send.provider,
                    "model": send.model,
                    "payload_sha256": send.payload_sha256,
                    "chars": send.chars,
                    "outbound_text": send.outbound_text,
                }
            )
        out_lines.append(e.model_dump_json(exclude_none=True))
    path.write_text("\n".join(out_lines) + "\n")
    return {
        "scenario": header.id,
        "model": model,
        "reply_chars": len(reply.text),
        "reply_preview": reply.text[:300],
    }


def storyboard(path: Path) -> str:
    """Human-readable walk-through of a scenario, for the README and the video script."""
    events = load(path)
    h = events[0]
    lines = [f"# UC{h.use_case}: {h.title}", "", h.summary, ""]
    for e in events[1:]:
        if isinstance(e, UserTurn):
            lines += [
                f"**{e.seq}. Practitioner ({e.practitioner_role}) asks:** {e.instruction}",
                "",
                "> " + e.note.replace("\n", "\n> "),
                "",
            ]
        elif isinstance(e, Expect):
            lines.append(f"- expect `{e.event}` {json.dumps(e.check)}: {e.why}")
        elif isinstance(e, Receive):
            lines += [
                f"**{e.seq}. Model reply ({e.source}{', ' + e.model if e.model else ''}):**",
                "",
                "> " + e.text.replace("\n", "\n> "),
                "",
            ]
        else:
            lines.append(
                f"- `{e.kind}` "
                + json.dumps(e.model_dump(exclude={"kind", "seq"}), ensure_ascii=False)[:300]
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python3 -m socareguard.scenarios")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("names", nargs="*")
    r = sub.add_parser("run")
    r.add_argument("names", nargs="*")
    r.add_argument(
        "--proxy",
        action="store_true",
        help="drive the real guard instead of echoing the storyboard",
    )
    r.add_argument(
        "--live", action="store_true", help="call the provider instead of using the script's reply"
    )
    rec = sub.add_parser(
        "record", help="run live through the proxy and write the reply back as a recorded fixture"
    )
    rec.add_argument("names", nargs="*")
    rec.add_argument("--model", default="openai/gpt-4.1-mini")
    s = sub.add_parser("storyboard")
    s.add_argument("names", nargs="*")
    sub.add_parser("build", help="write the four scenario scripts from scenarios/authoring.py")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        from socareguard.scenarios.authoring import build

        for p in build(SCENARIO_DIR):
            print(f"wrote {p}")
        return
    paths = [
        SCENARIO_DIR / (n if n.endswith(".jsonl") else f"{n}.jsonl") for n in a.names
    ] or sorted(SCENARIO_DIR.glob("*.jsonl"))
    rc = 0
    for p in paths:
        if a.cmd == "validate":
            probs = validate(p)
            print(f"{p.name}: {'ok' if not probs else '; '.join(probs)}")
            rc |= any(not x.startswith(WARNING) for x in probs)
        elif a.cmd == "run":
            res = run(p, mode="proxy" if a.proxy else "storyboard", live=a.live)
            print(json.dumps(res, indent=2, ensure_ascii=False))
            rc |= res["summary"]["fail"] > 0
        elif a.cmd == "record":
            print(json.dumps(record(p, a.model), indent=2, ensure_ascii=False))
        else:
            print(storyboard(p))
    sys.exit(rc)


if __name__ == "__main__":
    main()
