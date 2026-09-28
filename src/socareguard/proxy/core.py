"""The guarded request: one function used by the FastAPI app, the LiteLLM guardrail hooks,
the scenario replay and the metrics runs, so every path emits the same event stream."""

from __future__ import annotations

import hashlib
import os
import uuid

from dotenv import load_dotenv

load_dotenv()  # provider keys from .env for every entry point, not only the proxy
from dataclasses import dataclass, field
from typing import Any

from socareguard.inbound.leakcheck import leak_check
from socareguard.inbound.restore import restore
from socareguard.ledger import Ledger
from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack
from socareguard.scenarios.events import Action, Receive, Reidentify, Send
from socareguard.scenarios.events import Ledger as LedgerEvent
from socareguard.screen import rules

TRANSFER_BASIS = os.environ.get(
    "SOCAREGUARD_TRANSFER_BASIS",
    "pseudonymised transfer under the deployer's provider terms; the legal basis is "
    "stated by the deployer (default statement, not yet set for this deployment)",
)
BUILD = os.environ.get("SOCAREGUARD_BUILD", "")


def _git_short() -> str:
    try:
        import subprocess

        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


if not BUILD:
    BUILD = _git_short() or "unknown"


def _pack_sha256(pack_id: str) -> str:
    from socareguard.policy.loader import PACK_DIR

    p = PACK_DIR / f"{pack_id}.yaml"
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


@dataclass
class GuardedResult:
    session: str
    outbound_messages: list[dict[str, str]]
    reply_raw: str
    reply: str
    events: list[Any] = field(default_factory=list)
    flags: list[Any] = field(default_factory=list)
    decision: str = "pass"
    ledger_row: dict[str, Any] | None = None
    usage: dict[str, int] = field(default_factory=dict)
    replacements: list[dict[str, str]] = field(default_factory=list)
    withheld: bool = False  # the draft was withheld from the practitioner (escalation)
    reply_withheld: str = ""  # the re-identified draft kept on this server for the supervisor
    flags_withheld: list[Any] = field(default_factory=list)  # the full flags, for the supervisor
    recipients: list[dict[str, str]] = field(default_factory=list)


class Guard:
    """Holds the vault, ledger and detectors. ``run`` performs one guarded completion."""

    def __init__(
        self,
        vault: Vault | None = None,
        ledger: Ledger | None = None,
        use_presidio: bool = True,
        use_gliner: bool = True,
        screener=None,
    ):
        self.vault = vault or Vault()
        self.ledger = ledger or Ledger()
        self.use_presidio = use_presidio
        self.use_gliner = use_gliner
        if (
            screener is None
            and os.environ.get("SOCAREGUARD_SCREEN", "auto") != "off"
            and (os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
        ):
            from socareguard.screen.screener import Screener

            screener = Screener()
        self.screener = screener

    def outbound(
        self,
        messages: list[dict[str, str]],
        pack_id: str,
        session: str,
        seed: int | None = None,
        audience: str | None = None,
    ):
        pack = load_pack(pack_id)
        san = Sanitiser(self.vault, pack, self.use_presidio, self.use_gliner, audience=audience)
        out_msgs, events, known, seq = [], [], set(), 1
        payload_parts = []
        replacements: list[dict[str, str]] = []
        for m in messages:
            if m.get("content"):
                # Every role is sanitised, an earlier assistant turn included: a thread that
                # quotes a name back is still a transfer. The practitioner's instruction (first
                # paragraph of a user turn) is substituted but never generalised, so an attribute
                # cue such as "probation" there cannot rewrite the instruction itself.
                s = _sanitise_message(
                    san, str(m["content"]), session, seed, seq, instruction=m.get("role") == "user"
                )
                out_msgs.append({"role": m["role"], "content": s.text})
                events += s.events
                seq += 3
                known |= {h.text for h, _, _ in s.replacements}
                known |= {h.text for h in s.detection.entities}  # kept spans are known too
                replacements += [
                    {
                        "original": h.text,
                        "outbound": new,
                        "category": ("ATTRIBUTE" if h.category.startswith("ATTR:") else h.category),
                        "type": (
                            "ATTRIBUTE"
                            if h.category.startswith("ATTR:")
                            else "QUASI"
                            if h.category in {"AGE", "ESTATE", "SCHOOL", "FACILITY", "EMPLOYER"}
                            else "DIRECT"
                        ),
                        "kind": kind,
                        "rule": s.rule_ids.get((h.start, h.end)),
                    }
                    for h, new, kind in s.replacements
                ]
                payload_parts.append(s.text)
            else:
                out_msgs.append(m)
        payload = "\n".join(payload_parts)
        return (
            out_msgs,
            events,
            known,
            hashlib.sha256(payload.encode()).hexdigest(),
            payload,
            seq,
            replacements,
        )

    def inbound(
        self,
        reply_raw: str,
        session: str,
        known: set[str],
        pack_id: str,
        seq: int,
        instruction: str = "",
        context: str = "",
        source_text: str = "",
        audience: str | None = None,
    ):
        pack = load_pack(pack_id)
        r = restore(reply_raw, self.vault, session)
        lk = leak_check(
            reply_raw,
            r,
            self.vault,
            session,
            known,
            self.use_presidio,
            self.use_gliner,
            source_text=source_text,
            outbound_text=context,
        )
        flags, decision, events = [], "pass", []
        if self.screener is not None:
            # Screen the pseudonymised reply: the judge provider never sees an original identifier.
            # The screen event comes first in the stream because the screen reads the reply as
            # received, before re-identification; it takes the leak check's invented identifiers
            # (I13), which are found on the restored text and reported in the leakcheck event.
            flags, decision, events = self.screener.screen(
                reply_raw,
                pack,
                seq,
                instruction=instruction,
                leaks=lk.invented,
                context=context,
                audience=audience,
            )
        # A surrogate left in the re-identified draft gets its own card, so the annotate decision
        # it causes is never silent.
        left = rules.unrestored_surrogate(r.text, lk.unrestored, lk.partial)
        if left is not None:
            flags = [*flags, left]
        n = len(events)
        events += [
            Reidentify(
                seq=seq + n,
                n_restored=r.n_restored,
                ambiguous_generalised=r.ambiguous_generalised,
            ),
            lk.event(seq + n + 1),
        ]
        if (not lk.passed or lk.invented) and decision == "pass":
            decision = "annotate"
        return r, lk, flags, decision, events

    def run(
        self,
        messages: list[dict[str, str]],
        pack_id: str,
        model: str,
        session: str | None = None,
        reply_fixture: str | None = None,
        seed: int | None = None,
        provider_kwargs: dict | None = None,
        actor: str | None = None,
        audience: str | None = None,
        audience_header: str | None = None,
    ) -> GuardedResult:
        session = session or uuid.uuid4().hex[:12]
        # The audience decides how a named employer leaves: the header's value, or else the one
        # the instruction implies, as the screen reads it.
        resolved_audience = (
            audience
            if audience in ("internal", "external")
            else "external"
            if rules.audience_is_external(_instruction(messages), pack_id)
            else "internal"
        )
        out_msgs, events, known, payload_hash, payload, seq, replacements = self.outbound(
            messages, pack_id, session, seed, audience=resolved_audience
        )
        events.append(
            Send(
                seq=seq,
                provider=model.split("/")[0],
                model=model,
                payload_sha256=payload_hash,
                chars=len(payload),
                outbound_text=payload,
            )
        )
        seq += 1
        usage: dict[str, int] = {}
        if reply_fixture is not None:
            reply_raw = reply_fixture
            events.append(
                Receive(
                    seq=seq,
                    source="recorded",
                    provider=model.split("/")[0],
                    model=model,
                    text=reply_raw,
                )
            )
        else:
            reply_raw, usage = complete(model, out_msgs, **(provider_kwargs or {}))
            events.append(
                Receive(
                    seq=seq,
                    source="live",
                    provider=model.split("/")[0],
                    model=model,
                    text=reply_raw,
                )
            )
        seq += 1
        r, lk, flags, decision, in_events = self.inbound(
            reply_raw,
            session,
            known,
            pack_id,
            seq,
            instruction=_instruction(messages),
            context=payload,
            source_text="\n".join(str(m.get("content") or "") for m in messages),
            audience=audience,
        )
        events += in_events
        seq += len(in_events)
        events.append(Action(seq=seq, decision=decision, reason=_reason(lk, flags, decision)))
        # Flags were raised on the pseudonymised draft; the practitioner reads them re-identified.
        flags = [
            f.model_copy(
                update={
                    "evidence": restore(f.evidence, self.vault, session).text,
                    "rewrite": restore(f.rewrite, self.vault, session).text if f.rewrite else None,
                    "reason": restore(f.reason, self.vault, session).text if f.reason else "",
                }
            )
            for f in flags
        ]
        pack = load_pack(pack_id)
        withheld = decision == "escalate" and pack.override.escalate_cannot_be_overridden
        flags_full = list(flags)
        if withheld:
            # The flag cards and the event stream must not print what the draft withholds, in
            # either form: the pseudonymised draft is as sendable as the restored one.
            for e in events:
                if e.kind == "receive":
                    e.text = "[withheld with the draft; released to a supervisor]"
                if e.kind == "screen":
                    e.flags = [
                        f.model_copy(update={"evidence": "[withheld]", "rewrite": None})
                        for f in e.flags
                    ]
            flags = [
                f.model_copy(
                    update={
                        "evidence": "[withheld with the draft; released to a supervisor]",
                        "rewrite": None,
                    }
                )
                for f in flags
            ]
        # Every party that received the pseudonymised text, for the ledger.
        recipients = [{"role": "drafting model", "model": model}]
        screen_ev = next((e for e in in_events if e.kind == "screen"), None)
        if screen_ev is not None and screen_ev.judge_model:
            recipients.append({"role": "conduct judge", "model": screen_ev.judge_model})
        if screen_ev is not None and screen_ev.baseline_model:
            recipients.append(
                {"role": "harm-classifier baseline", "model": screen_ev.baseline_model}
            )
        row = self.ledger.append(
            {
                "session": session,
                "pack": pack_id,
                "pack_version": pack.version,
                "pack_sha256": _pack_sha256(pack_id),
                "rules_fired": sorted(
                    {
                        r["rule"]
                        for e in events
                        if e.kind == "generalise"
                        for r in e.rules
                        if r.get("rule")
                    }
                ),
                "build": BUILD,
                "actor": actor or "unattributed",
                "replayed_reply": reply_fixture is not None,
                "provider": model.split("/")[0],
                "model": model,
                "recipients": recipients,
                "transfer_basis": TRANSFER_BASIS,
                "payload_sha256": payload_hash,
                "payload_chars": len(payload),
                "n_identifiers_substituted": sum(
                    e.n_spans for e in events if e.kind == "substitute"
                ),
                "n_generalised": sum(len(e.rules) for e in events if e.kind == "generalise"),
                "n_withheld": sum(
                    getattr(e, "n_withheld", 0) for e in events if e.kind == "substitute"
                ),
                "audience": next(
                    (e.audience for e in in_events if e.kind == "screen"), "not screened"
                ),
                "audience_source": "header" if audience_header else "instruction",
                "employer_treatment": _employer_treatment(replacements, resolved_audience),
                "n_restored": r.n_restored,
                "leakcheck_passed": lk.passed,
                "leakcheck_detail": {
                    "echoed": len(lk.original_echoed),
                    "unrestored": list(lk.unrestored),
                    "ambiguous_generalised": list(r.ambiguous_generalised),
                    "partial": list(lk.partial),
                },
                "n_invented": len(lk.invented),
                "flags": [f.label for f in flags],
                "decision": decision,
                "withheld": withheld,
                "usage": usage,
            }
        )
        events.append(
            LedgerEvent(
                seq=seq + 1,
                row_sha256=row["row_sha256"],
                prev_sha256=row["prev_sha256"],
                fields=row,
            )
        )
        return GuardedResult(
            replacements=replacements,
            session=session,
            outbound_messages=out_msgs,
            reply_raw=reply_raw,
            reply=_withheld_notice(flags, session) if withheld else r.text,
            withheld=withheld,
            reply_withheld=r.text if withheld else "",
            flags_withheld=flags_full if withheld else [],
            recipients=recipients,
            events=events,
            flags=flags,
            decision=decision,
            ledger_row=row,
            usage=usage,
        )

    def override(
        self,
        session: str,
        by: str,
        flag_labels: list[str],
        reason: str,
        pack_id: str,
        request_row_sha256: str | None = None,
        kind: str = "override",
        attested: bool = False,
        draft_sha256: str | None = None,
    ) -> dict[str, Any]:
        pack = load_pack(pack_id)
        if pack.override.requires_reason and not reason.strip():
            raise ValueError("override requires a reason")
        if pack.override.escalate_cannot_be_overridden:
            for f in flag_labels:
                if pack.action_for(f) == "escalate":
                    raise ValueError(
                        f"{f} escalates to supervisory review and cannot be overridden by the practitioner"
                    )
        return self.ledger.append(
            {
                "session": session,
                "pack": pack_id,
                "pack_version": pack.version,
                "pack_sha256": _pack_sha256(pack_id),
                "build": BUILD,
                "actor": by,
                "actor_attested": attested,
                "override_by": by,
                "override_reason": reason,
                "flags": flag_labels,
                "draft_sha256": draft_sha256,
                "request_row_sha256": request_row_sha256,
                "decision": kind,
            }
        )


def _sanitise_message(
    san: Sanitiser,
    content: str,
    session: str,
    seed: int | None,
    seq: int,
    instruction: bool = True,
):
    """One pass over the whole message. In a user turn, attribute generalisation is suppressed
    inside the first paragraph, which is the practitioner's instruction, so a cue such as
    "probation" there cannot rewrite the instruction; entities in the instruction are still
    substituted. Other roles are treated as note text throughout."""
    head, sep, _body = content.partition("\n\n")
    floor = len(head) + len(sep) if sep and instruction else 0
    return san.sanitise(content, session=session, seed=seed, seq_start=seq, attribute_floor=floor)


def _employer_treatment(replacements: list[dict], audience: str) -> str | None:
    """How a named employer left the premises, for the ledger row and the panel: a reversible
    surrogate (internal audience, restored in the draft) or its kind (external audience, not
    restored). None when the note names no employer."""
    kinds = {r["kind"] for r in replacements if r["category"] == "EMPLOYER"}
    if "surrogate" in kinds:
        return f"surrogate, restored in the draft ({audience} audience)"
    if "generalised" in kinds:
        return f"generalised to its kind, not restored ({audience} audience)"
    return None


def _withheld_notice(flags, session: str) -> str:
    labels = ", ".join(sorted({f.label for f in flags if f.severity == "escalate"})) or "escalation"
    return (
        f"[SoCareGuard withheld this draft: {labels} escalates to supervisory review and cannot be "
        f"overridden by the practitioner. The draft is retained on this server under session "
        f"{session} for a supervisor to release.]"
    )


def _instruction(messages: list[dict[str, str]]) -> str:
    """The practitioner's ask: the first line of the last user message."""
    for m in reversed(messages):
        if m.get("role") == "user" and m.get("content"):
            return str(m["content"]).strip().split("\n")[0][:300]
    return ""


def _reason(lk, flags, decision: str) -> str:
    if decision == "pass":
        return "no leak, no conduct flag"
    parts = []
    if not lk.passed:
        parts.append(
            f"leak check: {len(lk.original_echoed)} echoed, {len(lk.unrestored)} unrestored"
            + (f", {len(lk.partial)} restored in part and left whole" if lk.partial else "")
        )
    if lk.invented:
        parts.append(f"{len(lk.invented)} identifier(s) invented by the model")
    if flags:
        parts.append("flags: " + ", ".join(f.label for f in flags))
    return "; ".join(parts)


def complete(model: str, messages: list[dict[str, str]], **kwargs) -> tuple[str, dict[str, int]]:
    import litellm

    litellm.suppress_debug_info = True
    litellm.drop_params = True  # e.g. Anthropic models that only accept temperature=1
    resp = litellm.completion(model=model, messages=messages, **kwargs)
    text = (resp.choices[0].message.content or "").strip()
    u = getattr(resp, "usage", None)
    usage = (
        {
            "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
            "total_tokens": (getattr(u, "prompt_tokens", 0) or 0)
            + (getattr(u, "completion_tokens", 0) or 0),
        }
        if u
        else {}
    )
    return text, usage
