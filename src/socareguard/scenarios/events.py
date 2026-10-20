"""Event schema for scenario scripts and for the proxy's structured log.

A scenario file is JSONL. The first line is a ``scenario`` header. Input lines
(``user_turn``, ``receive`` with ``source: recorded``) drive a replay, and ``expect`` lines
assert what the pipeline must emit. Every other kind is an event the pipeline logs.
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
    recorded_screen: dict[str, Any] | None = Field(
        default=None,
        description="the screen's verdict in a recorded run, shown in the panel as a reference",
    )


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
    n_spans: int = Field(description="spans replaced by a surrogate")
    n_entities: int
    n_generalised: int = 0
    n_kept: int = Field(0, description="attribute spans with no rule in this pack, sent as typed")
    n_withheld: int = Field(0, description="never_leak spans withheld outright")
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
    ambiguous_generalised: list[str] = Field(
        default_factory=list,
        description="generalised phrases left as they are because two originals share them",
    )


class LeakCheck(BaseModel):
    kind: Literal["leakcheck"] = "leakcheck"
    seq: int
    passed: bool = Field(
        description="no original identifier echoed and no surrogate left unrestored"
    )
    leaks: list[DetectedSpan] = Field(default_factory=list)
    n_echoed: int = 0
    n_invented: int = Field(
        0, description="identifiers the model introduced; reported as I13, not as a leak"
    )
    n_unrestored: int = 0
    unrestored: list[str] = Field(default_factory=list)
    partial: list[str] = Field(
        default_factory=list,
        description="surrogates the reply reformatted, left whole rather than restored in part",
    )
    ambiguous_people: list[str] = Field(
        default_factory=list,
        description=(
            "titled surnames in the reply (as written) that could be either of two people in one "
            "household; restored to the shared surname and marked"
        ),
    )


class Flag(BaseModel):
    label: str
    clause: str
    severity: Literal["info", "annotate", "regenerate", "escalate"]
    evidence: str
    rewrite: str | None = None
    name: str = ""  # the category's plain-language name, for the practitioner
    reason: str = ""  # the judge's one-sentence reason
    confidence: float | None = None


class Screen(BaseModel):
    kind: Literal["screen"] = "screen"
    seq: int
    flags: list[Flag]
    baseline_flags: list[str] = Field(
        default_factory=list, description="what a generic harm screen flagged, for contrast"
    )
    judge_model: str | None = None
    baseline_model: str | None = None
    audience: Literal["internal", "care-team", "external"] = "internal"
    note_source: Literal["live", "recorded"] = Field(
        "live",
        description="the source note the judge read: this request's outbound text, or for a "
        "replayed reply the pseudonymised text that its model was given when it was recorded",
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
