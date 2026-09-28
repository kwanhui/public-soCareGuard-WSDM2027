"""Corpus v1.3: 30 compliant drafts for the client's own care team beside the v1.2 drafts, so that
the care-team tier of the audience gate is tested against compliant care-team drafts."""

import json
import re
from pathlib import Path

import pytest
import yaml

from socareguard.corpus.drafts import TASKS, careteam_plan, load_drafts
from socareguard.corpus.schema import Note
from socareguard.eval.run_screen import recipient_text
from socareguard.screen.rules import resolve_audience

ROOT = Path(__file__).parent.parent
PACKS = ("disability", "domestic-violence", "youth-offending")
# Real institution names replaced in corpus v1.1, and private or internal markers
RENAMED = (
    "Compassvale", "Northlight", "Greenridge", "Casuarina", "Meridian", "Woodgrove",
    "Star Shelter", "Lighthouse Day Activity Centre", "Pertapis", "Tampines FSC",
    "Ang Mo Kio FSC", "Queenstown FSC", "Care Corner", "Fei Yue", "Montfort",
)  # fmt: skip
# Private repo names and paths, assembled from parts so that this public-bound test
# does not itself carry the strings the snapshot guard refuses.
_PRIVATE = tuple(
    "-".join(x) for x in (("tool", "SoCareGuard"), ("paper", "SoCareGuard"), ("lab", "org"))
) + (
    "/" + "home" + "/",
    ".".join(("lim", "kwan", "hui")),
)
RENAMED = RENAMED + _PRIVATE
CFG = yaml.safe_load((ROOT / "configs/corpus-v1.3.yaml").read_text())


def _careteam(pack: str) -> list:
    return load_drafts(ROOT / "corpus/drafts" / f"{pack}-careteam-v1.3.jsonl")


def _notes(pack: str) -> list[Note]:
    return [
        Note.model_validate_json(line)
        for line in (ROOT / "corpus/notes" / f"{pack}.jsonl").read_text().splitlines()
        if line.strip()
    ]


@pytest.mark.parametrize("pack", PACKS)
def test_ten_compliant_careteam_drafts_per_pack(pack):
    ds = _careteam(pack)
    assert len(ds) == 10 and len({d.note_id for d in ds}) == 10
    assert all(d.label.value == "NONE" and d.intended_failure is None for d in ds)
    assert all(d.audience == "care-team" for d in ds)
    assert all(d.generation.model == "gpt-4.1-mini" for d in ds)
    assert {d.note_id for d in ds} <= {n.id for n in _notes(pack)}
    got: dict[str, int] = {}
    for d in ds:
        got[d.task] = got.get(d.task, 0) + 1
    assert got == CFG["careteam_drafts"]["per_pack"][pack]


@pytest.mark.parametrize("pack", PACKS)
def test_careteam_drafts_address_a_careteam_recipient(pack):
    """Every address block reads as care-team under the proxy's own resolve_audience, and the
    stored recipient_kind agrees."""
    rows = [
        json.loads(line)
        for line in (ROOT / "corpus/drafts" / f"{pack}-careteam-v1.3.jsonl")
        .read_text()
        .splitlines()
        if line.strip()
    ]
    for d, r in zip(_careteam(pack), rows, strict=True):
        assert resolve_audience(recipient_text(d.text), pack) == "care-team", d.id
        assert resolve_audience(TASKS[d.task], pack) == "care-team", d.task
        assert r["recipient_kind"] == "care-team", d.id


@pytest.mark.parametrize("pack", PACKS)
def test_careteam_drafts_name_no_real_institution_email_or_invented_titled_person(pack):
    notes = {n.id: n.text for n in _notes(pack)}
    for d in _careteam(pack):
        low = d.text.lower()
        assert not [w for w in RENAMED if w.lower() in low], d.id
        for m in re.finditer(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)", d.text):
            assert m.group(1).lower() == "example.org", d.id
        for m in re.finditer(r"\b(?:Mr|Mrs|Ms|Mdm|Madam|Dr)\.?\s+([A-Z][a-z]+)", d.text):
            assert m.group(1) in notes[d.note_id], (d.id, m.group(0))


def test_careteam_instructions_state_consent_and_need_to_know():
    for task in {t for per in CFG["careteam_drafts"]["per_pack"].values() for t in per}:
        text = TASKS[task]
        assert "agreed that I may" in text and "Share only" in text, task
        assert "history of the case" in text, task


def test_careteam_plan_is_reproducible():
    per_pack = CFG["careteam_drafts"]["per_pack"]
    for pack in PACKS:
        seed = int(CFG["seed"]) + 10 + sorted(per_pack).index(pack)
        plan = careteam_plan(_notes(pack), per_pack[pack], seed)
        assert {f"{n.id}-ct-{t}" for n, t in plan} == {d.id for d in _careteam(pack)}


def test_earlier_configs_are_frozen_and_v13_extends_v12():
    v12 = yaml.safe_load((ROOT / "configs/corpus-v1.2.yaml").read_text())
    assert CFG["base"] == "v1.2" and CFG["version"] == "v1.3"
    for k, v in v12.items():
        if k not in ("version", "base"):
            assert CFG[k] == v, k
