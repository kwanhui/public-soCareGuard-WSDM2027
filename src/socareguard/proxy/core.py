"""The guarded request: one function used by the FastAPI app, the LiteLLM guardrail hooks,
the scenario replay and the metrics runs, so every path emits the same event stream."""

from __future__ import annotations

import hashlib
import os
import uuid
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

TRANSFER_BASIS = os.environ.get(
    "SOCAREGUARD_TRANSFER_BASIS",
    "PDPA s.26 with pseudonymised payload; provider under contractual data-intermediary terms",
)


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


class Guard:
    """Holds the vault, ledger and detectors; ``run`` performs one guarded completion."""

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
            and os.environ.get("ANTHROPIC_API_KEY")
        ):
            from socareguard.screen.screener import Screener

            screener = Screener()
        self.screener = screener

    def outbound(
        self, messages: list[dict[str, str]], pack_id: str, session: str, seed: int | None = None
    ):
        pack = load_pack(pack_id)
        san = Sanitiser(self.vault, pack, self.use_presidio, self.use_gliner)
        out_msgs, events, known, seq = [], [], set(), 1
        payload_parts = []
        replacements: list[dict[str, str]] = []
        for m in messages:
            if m.get("role") in ("user", "system") and m.get("content"):
                # The practitioner's instruction (first paragraph) is substituted but never
                # generalised: an attribute cue such as "probation" in an instruction must not
                # rewrite the instruction itself. Attributes are generalised in the note body.
                s = _sanitise_message(san, m["content"], session, seed, seq)
                out_msgs.append({"role": m["role"], "content": s.text})
                events += s.events
                seq += 3
                known |= {h.text for h, _, _ in s.replacements}
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
                    }
                    for h, new, kind in s.replacements
                ]
                payload_parts.append(s.text)
            else:
                out_msgs.append(m)
        payload = "\n".join(payload_parts)
        self._last_replacements = replacements
        return out_msgs, events, known, hashlib.sha256(payload.encode()).hexdigest(), payload, seq

    def inbound(
        self,
        reply_raw: str,
        session: str,
        known: set[str],
        pack_id: str,
        seq: int,
        instruction: str = "",
        context: str = "",
    ):
        pack = load_pack(pack_id)
        r = restore(reply_raw, self.vault, session)
        lk = leak_check(
            reply_raw, r, self.vault, session, known, self.use_presidio, self.use_gliner
        )
        events = [Reidentify(seq=seq, n_restored=r.n_restored), lk.event(seq + 1)]
        flags, decision, screen_events = [], "pass", []
        if self.screener is not None:
            # Screen the pseudonymised reply: the judge provider never sees an original identifier.
            flags, decision, screen_events = self.screener.screen(
                reply_raw,
                pack,
                seq + 2,
                instruction=instruction,
                leaks=lk.invented,
                context=context,
            )
            events += screen_events
        if not lk.passed and decision == "pass":
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
    ) -> GuardedResult:
        session = session or uuid.uuid4().hex[:12]
        out_msgs, events, known, payload_hash, payload, seq = self.outbound(
            messages, pack_id, session, seed
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
        )
        events += in_events
        seq += len(in_events)
        events.append(Action(seq=seq, decision=decision, reason=_reason(lk, flags, decision)))
        row = self.ledger.append(
            {
                "session": session,
                "pack": pack_id,
                "provider": model.split("/")[0],
                "model": model,
                "transfer_basis": TRANSFER_BASIS,
                "payload_sha256": payload_hash,
                "payload_chars": len(payload),
                "n_identifiers_substituted": sum(
                    e.n_spans for e in events if e.kind == "substitute"
                ),
                "n_generalised": sum(len(e.rules) for e in events if e.kind == "generalise"),
                "n_restored": r.n_restored,
                "leakcheck_passed": lk.passed,
                "flags": [f.label for f in flags],
                "decision": decision,
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
            replacements=list(getattr(self, "_last_replacements", [])),
            session=session,
            outbound_messages=out_msgs,
            reply_raw=reply_raw,
            reply=r.text,
            events=events,
            flags=flags,
            decision=decision,
            ledger_row=row,
            usage=usage,
        )

    def override(
        self, session: str, by: str, flag_labels: list[str], reason: str, pack_id: str
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
                "override_by": by,
                "override_reason": reason,
                "flags": flag_labels,
                "decision": "override",
            }
        )


def _sanitise_message(san: Sanitiser, content: str, session: str, seed: int | None, seq: int):
    """One pass over the whole message. Attribute generalisation is suppressed inside the first
    paragraph, which is the practitioner's instruction, so a cue such as "probation" there cannot
    rewrite the instruction; entities in the instruction are still substituted."""
    head, sep, _body = content.partition("\n\n")
    floor = len(head) + len(sep) if sep else 0
    return san.sanitise(content, session=session, seed=seed, seq_start=seq, attribute_floor=floor)


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
        parts.append(f"leak check: {len(lk.invented)} invented, {len(lk.original_echoed)} echoed")
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
            "prompt_tokens": getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
        }
        if u
        else {}
    )
    return text, usage
