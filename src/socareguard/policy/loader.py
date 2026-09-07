"""Load and validate policy packs from ``policy-packs/*.yaml``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from socareguard.taxonomy import BY_ID

PACK_DIR = Path(__file__).resolve().parents[3] / "policy-packs"


class AttributeRule(BaseModel):
    key: str
    generalise_to: str


class QuasiRule(BaseModel):
    category: str
    generalise_to: str
    kinds: list[str] = Field(default_factory=list)


class NeverLeak(BaseModel):
    label: str
    pattern: str | None = None  # regex; when present the span is withheld outbound
    withhold_as: str | None = None  # the placeholder text; defaults to "[withheld: <label>]"


class Outbound(BaseModel):
    attributes: list[AttributeRule]
    quasi_identifiers: list[QuasiRule]
    never_leak: list[NeverLeak] = Field(default_factory=list)

    @field_validator("never_leak", mode="before")
    @classmethod
    def _coerce(cls, v):
        return [{"label": x} if isinstance(x, str) else x for x in (v or [])]


class CategoryAction(BaseModel):
    id: str
    default_action: str
    note: str | None = None


class SettingRule(BaseModel):
    id: str
    name: str
    grounded: bool
    clause: str | None = None
    note: str | None = None


class Inbound(BaseModel):
    categories: list[CategoryAction]
    setting_rules: list[SettingRule]


class Override(BaseModel):
    allowed: bool
    requires_reason: bool
    escalate_cannot_be_overridden: bool


class Pack(BaseModel):
    id: str
    label: str
    version: int
    status: str
    legal_anchors: list[str]
    outbound: Outbound
    inbound: Inbound
    override: Override
    consent_architecture: dict | None = None

    def attribute_rule(self, key: str) -> AttributeRule | None:
        return next((r for r in self.outbound.attributes if r.key == key), None)

    def quasi_rule(self, category: str) -> QuasiRule | None:
        return next((r for r in self.outbound.quasi_identifiers if r.category == category), None)

    def action_for(self, category_id: str) -> str | None:
        return next(
            (c.default_action for c in self.inbound.categories if c.id == category_id), None
        )


@lru_cache(maxsize=8)
def load_pack(pack_id: str, pack_dir: Path | None = None) -> Pack:
    path = (pack_dir or PACK_DIR) / f"{pack_id}.yaml"
    pack = Pack.model_validate(yaml.safe_load(path.read_text()))
    for c in pack.inbound.categories:
        if c.id not in BY_ID:
            raise ValueError(f"{path}: unknown conduct category {c.id}")
    return pack


def available_packs(pack_dir: Path | None = None) -> list[str]:
    return sorted(p.stem for p in (pack_dir or PACK_DIR).glob("*.yaml"))
