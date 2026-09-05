"""Pydantic models for the corpus: notes, gold spans, conduct drafts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SpanType(str, Enum):
    """TAB-style span typing.

    DIRECT: identifies the person on its own (name, NRIC, phone, address, DOB, case ref).
    QUASI: identifies in combination (school, estate, age, employer, facility).
    ATTRIBUTE: a sensitive attribute that is the target of generalisation rather
    than substitution (disability, DV disclosure, minor status, PPO status, offence).
    """

    DIRECT = "DIRECT"
    QUASI = "QUASI"
    ATTRIBUTE = "ATTRIBUTE"


# Placeholder key -> (span type, category). Categories are the labels reported in metrics.
PLACEHOLDER_CATEGORIES: dict[str, tuple[SpanType, str]] = {
    "CLIENT_NAME": (SpanType.DIRECT, "NAME"),
    "CLIENT_FIRST": (SpanType.DIRECT, "NAME"),
    "CLIENT_TITLE": (SpanType.DIRECT, "NAME"),
    "TP_NAME": (SpanType.DIRECT, "THIRD_PARTY_NAME"),
    "TP_FIRST": (SpanType.DIRECT, "THIRD_PARTY_NAME"),
    "NRIC": (SpanType.DIRECT, "NRIC"),
    "DOB": (SpanType.DIRECT, "DOB"),
    "ADDRESS": (SpanType.DIRECT, "ADDRESS"),
    "PHONE": (SpanType.DIRECT, "PHONE"),
    "CASE_REF": (SpanType.DIRECT, "CASE_REF"),
    "SCHOOL": (SpanType.QUASI, "SCHOOL"),
    "ESTATE": (SpanType.QUASI, "ESTATE"),
    "AGE": (SpanType.QUASI, "AGE"),
    "EMPLOYER": (SpanType.QUASI, "EMPLOYER"),
    "FACILITY": (SpanType.QUASI, "FACILITY"),
    "ATTR": (SpanType.ATTRIBUTE, "ATTRIBUTE"),
}

ATTRIBUTE_KEYS = {
    "disability",
    "diagnosis",
    "dv_disclosure",
    "minor",
    "ppo",
    "offence",
    "safety_plan",
    "capacity",
}

CODE_SWITCH_LANGS = {"singlish", "malay", "mandarin", "tamil"}


class Span(BaseModel):
    start: int
    end: int
    text: str
    type: SpanType
    category: str
    placeholder: str = Field(
        description="Placeholder key as written by the generator, e.g. CLIENT_NAME"
    )
    arg: str | None = Field(
        default=None, description="Placeholder argument, e.g. a third-party role or attribute key"
    )
    entity_id: str = Field(
        description="Stable id shared by every span of the same underlying entity in the note"
    )
    origin: str | None = Field(
        default=None,
        description="Name origin for NAME spans: chinese, malay, indian, eurasian, western",
    )


class CodeSwitch(BaseModel):
    start: int
    end: int
    lang: str
    text: str


class GenerationMeta(BaseModel):
    provider: str
    model: str
    prompt_hash: str
    temperature: float
    created_at: datetime
    git_commit: str | None = None


class Brief(BaseModel):
    """What the generator was asked to write. Stored with the note so every field is auditable."""

    pack: str
    note_type: str
    practitioner_role: str
    client_gender: str
    client_age: int
    client_origin: str
    presenting_concern: str
    required_placeholders: list[str]
    attributes: list[str]
    code_switch_lang: str | None = None
    note_date: str


class Template(BaseModel):
    """Layer-1 output: the note as written by the model, placeholders intact."""

    id: str
    pack: str
    seed: int
    brief: Brief
    template_text: str
    generation: GenerationMeta
    validation_errors: list[str] = Field(default_factory=list)


class Note(BaseModel):
    """Layer-2 output: the injected note with gold spans."""

    id: str
    pack: str
    seed: int
    brief: Brief
    template_text: str
    text: str
    spans: list[Span]
    code_switches: list[CodeSwitch] = Field(default_factory=list)
    generation: GenerationMeta
    injection_commit: str | None = None

    @model_validator(mode="after")
    def _spans_reslice(self) -> Note:
        for s in self.spans:
            if self.text[s.start : s.end] != s.text:
                raise ValueError(
                    f"span {s.placeholder} at {s.start}:{s.end} does not re-slice to its text"
                )
        for c in self.code_switches:
            if self.text[c.start : c.end] != c.text:
                raise ValueError(f"code-switch at {c.start}:{c.end} does not re-slice")
        return self


class ConductLabel(str, Enum):
    NONE = "NONE"
    I1_EMOTIVE_LANGUAGE = "I1"
    I2_DISRESPECTFUL_LANGUAGE = "I2"
    I3_FABRICATED_CONTENT = "I3"
    I4_DISCRIMINATORY_FRAMING = "I4"
    I5_SELF_DETERMINATION_OVERRIDE = "I5"
    I6_RISK_CARVEOUT_MISSED = "I6"
    I7_BOUNDARY_VIOLATION = "I7"
    I8_OUT_OF_SCOPE_ADVICE = "I8"
    I9_UNREALISTIC_EXPECTATIONS = "I9"
    I10_DISCLOSURE_WITHOUT_CONSENT = "I10"
    I11_CONSENT_CAPACITY_MISMATCH = "I11"
    I12_CONTRARY_TO_POLICY = "I12"
    I13_REIDENTIFYING_DETAIL = "I13"
    I14_PROTECTED_YOUTH_IDENTIFICATION = "I14"
    OVER_CAUTION = "OVER_CAUTION"


class Draft(BaseModel):
    """Layer-3 output: a model draft produced from a note, with a generation-intent label.

    The label records what the generator was instructed to do. It is not an expert
    annotation and the corpus README says so.
    """

    id: str
    note_id: str
    pack: str
    task: str
    label: ConductLabel
    intended_failure: str | None = None
    text: str
    generation: GenerationMeta
