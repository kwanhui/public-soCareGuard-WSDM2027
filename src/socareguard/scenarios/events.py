"""Event schema for scenario scripts and for the proxy's structured log.

A scenario file is JSONL. The first line is a ``scenario`` header. Input lines
(``user_turn``, ``receive`` with ``source: recorded``) drive a replay; ``expect`` lines
assert what the pipeline must emit; every other kind is an event the pipeline logs.
The same models are used by the proxy at run time, so a live run and a replay produce
comparable streams.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter


class ScenarioHeader(BaseModel):
    kind: Literal["scenario"] = "scenario"
    id: str
    title: str
    pack: str
    use_case: int
    summary: str
    corpus_note_id: str | None = None


class UserTurn(BaseModel):
    kind: Literal["user_turn"] = "user_turn"
    seq: int
    practitioner_role: str
    instruction: str = Field(description="What the practitioner asks the assistant to do")
    note: str = Field(description="The raw note as typed, before anything leaves the premises")


class DetectedSpan(BaseModel):
    start: int
    end: int
    text: str
    type: str
    category: str
    detector: str
    score: float | None = None


class Detect(BaseModel):
    kind: Literal["detect"] = "detect"
    seq: int
    spans: list[DetectedSpan]


class Generalise(BaseModel):
    kind: Literal["generalise"] = "generalise"
    seq: int
    rules: list[dict[str, Any]] = Field(
        description="attribute or quasi span -> banded form, with the policy-pack rule id"
    )


class Substitute(BaseModel):
    kind: Literal["substitute"] = "substitute"
    seq: int
    n_spans: int
    n_entities: int
    vault_session: str


class Send(BaseModel):
    kind: Literal["send"] = "send"
    seq: int
    provider: str
    model: str
    payload_sha256: str
    chars: int
    outbound_text: str | None = Field(
        default=None, description="The pseudonymised payload, for the storyboard"
    )


class Receive(BaseModel):
    kind: Literal["receive"] = "receive"
    seq: int
    source: Literal["recorded", "live", "authored"]
    provider: str | None = None
    model: str | None = None
    recorded_at: str | None = None
    text: str


class Reidentify(BaseModel):
    kind: Literal["reidentify"] = "reidentify"
    seq: int
    n_restored: int


class LeakCheck(BaseModel):
    kind: Literal["leakcheck"] = "leakcheck"
    seq: int
    passed: bool
    leaks: list[DetectedSpan] = Field(default_factory=list)


class Flag(BaseModel):
    label: str
    clause: str
    severity: Literal["info", "annotate", "regenerate", "escalate"]
    evidence: str
    rewrite: str | None = None


class Screen(BaseModel):
    kind: Literal["screen"] = "screen"
    seq: int
    flags: list[Flag]
    baseline_flags: list[str] = Field(
        default_factory=list, description="what a generic harm screen flagged, for contrast"
    )


class Action(BaseModel):
    kind: Literal["action"] = "action"
    seq: int
    decision: Literal["pass", "annotate", "regenerate", "escalate"]
    reason: str


class Override(BaseModel):
    kind: Literal["override"] = "override"
    seq: int
    by: str
    flag_labels: list[str]
    reason: str


class Ledger(BaseModel):
    kind: Literal["ledger"] = "ledger"
    seq: int
    row_sha256: str
    prev_sha256: str | None
    fields: dict[str, Any]


class Expect(BaseModel):
    kind: Literal["expect"] = "expect"
    seq: int
    event: str
    check: dict[str, Any] = Field(description="Assertion spec evaluated by scenarios.replay.check")
    why: str


Event = Annotated[
    ScenarioHeader
    | UserTurn
    | Detect
    | Generalise
    | Substitute
    | Send
    | Receive
    | Reidentify
    | LeakCheck
    | Screen
    | Action
    | Override
    | Ledger
    | Expect,
    Field(discriminator="kind"),
]
EVENT_ADAPTER: TypeAdapter[Any] = TypeAdapter(Event)
