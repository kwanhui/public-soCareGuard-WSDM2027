"""Corpus v1.2: 90 compliant drafts for an external reader beside the v1.1
drafts, so that the audience gate is tested against compliant external drafts."""

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

from socareguard.corpus.drafts import TASKS, external_plan, load_drafts
from socareguard.corpus.schema import Note
from socareguard.eval.run_screen import load_screen_drafts, row_is_external
from socareguard.screen.rules import audience_is_external

ROOT = Path(__file__).parent.parent
PACKS = ("disability", "domestic-violence", "youth-offending")
# Real institution names replaced in corpus v1.1, and internal markers, kept as truncated SHA-256
# hashes of their lower-case word sequences so that this public test does not itself carry them.
_FORBIDDEN = frozenset(
    (
        "047a6d03a9c6f57f",
        "08fe0e9daa4ee453",
        "1d46dbd0cf27d34e",
        "22a682433f151925",
        "25799de66fd133f5",
        "2f97c413b291cec3",
        "3adeab0df544f83f",
        "4291cf072b988233",
        "4ca1c5c9f8427eeb",
        "5209a515663eb055",
        "67742854a6c175d1",
        "78928d8201a4d0a0",
        "7be32ebbedae9fe0",
        "7ed1a828d670dc38",
        "920bce366226dadd",
        "b6c4ac412ac88223",
        "b8ab9cf843c13e4c",
        "cc4f787ca8ead19c",
        "cd34eae204a1511e",
    )
)


def _forbidden_in(text: str) -> bool:
    """Whether the text names one of the replaced institutions or an internal marker."""
    low = text.lower()
    if "/" + "home" + "/" in low:
        return True
    words = re.findall(r"[a-z0-9]+", low)
    for k in range(1, 5):
        for i in range(len(words) - k + 1):
            gram = " ".join(words[i : i + k])
            if hashlib.sha256(gram.encode()).hexdigest()[:16] in _FORBIDDEN:
                return True
    return False


def _external(pack: str) -> list:
    return load_drafts(ROOT / "corpus/drafts" / f"{pack}-external-v1.2.jsonl")


@pytest.mark.parametrize("pack", PACKS)
def test_thirty_compliant_external_drafts_per_pack(pack):
    ds = _external(pack)
    assert len(ds) == 30 and len({d.note_id for d in ds}) == 30
    assert all(d.label.value == "NONE" and d.audience == "external" for d in ds)
    assert all(d.generation.model == "gpt-4.1-mini" for d in ds)
    notes = {
        Note.model_validate_json(line).id
        for line in (ROOT / "corpus/notes" / f"{pack}.jsonl").read_text().splitlines()
        if line.strip()
    }
    assert {d.note_id for d in ds} <= notes
    cfg = yaml.safe_load((ROOT / "configs/corpus-v1.2.yaml").read_text())
    want = cfg["external_drafts"]["per_pack"][pack]
    got: dict[str, int] = {}
    for d in ds:
        got[d.task] = got.get(d.task, 0) + 1
    assert got == want


@pytest.mark.parametrize("pack", PACKS)
def test_external_drafts_name_no_real_institution_email_or_invented_titled_person(pack):
    notes = {
        n.id: n.text
        for n in (
            Note.model_validate_json(line)
            for line in (ROOT / "corpus/notes" / f"{pack}.jsonl").read_text().splitlines()
            if line.strip()
        )
    }
    for d in _external(pack):
        assert not _forbidden_in(d.text), d.id
        assert not re.search(r"[\w.+-]+@[\w-]+\.\w", d.text), d.id
        for m in re.finditer(r"\b(?:Mr|Mrs|Ms|Mdm|Madam|Dr)\.?\s+([A-Z][a-z]+)", d.text):
            assert m.group(1) in notes[d.note_id], (d.id, m.group(0))


def test_external_tasks_read_as_external_and_the_plan_is_reproducible():
    for task in ("referral_note", "school_letter", "employer_letter"):
        assert audience_is_external(TASKS[task]), task
    assert not audience_is_external(TASKS["summary_plan"])
    cfg = yaml.safe_load((ROOT / "configs/corpus-v1.2.yaml").read_text())
    notes = [
        Note.model_validate_json(line)
        for line in (ROOT / "corpus/notes/domestic-violence.jsonl").read_text().splitlines()
        if line.strip()
    ]
    per = cfg["external_drafts"]["per_pack"]["domestic-violence"]
    plan = external_plan(
        notes,
        per,
        int(cfg["seed"]) + sorted(cfg["external_drafts"]["per_pack"]).index("domestic-violence"),
    )
    assert {f"{n.id}-ext-{t}" for n, t in plan} == {d.id for d in _external("domestic-violence")}


def test_screen_loads_v12_as_v11_plus_the_external_drafts(monkeypatch):
    monkeypatch.chdir(ROOT)
    v11 = load_screen_drafts(PACKS, corpus="v1.1")
    v12 = load_screen_drafts(PACKS, corpus="v1.2")
    assert len(v11) == 600 and len(v12) == 690
    assert [d.id for d in v12 if d.audience is None] == [d.id for d in v11]
    row = {"task": "summary_plan", "audience": "external"}
    assert row_is_external(row) and not row_is_external({"task": "summary_plan"})


def test_v11_draft_files_are_unchanged():
    """The v1.1 drafts keep their label counts; v1.2 only appends files."""
    counts = {}
    for p in PACKS:
        for line in (ROOT / "corpus/drafts" / f"{p}.jsonl").read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                assert "audience" not in r
                counts[r["label"]] = counts.get(r["label"], 0) + 1
    assert counts["NONE"] == 300 and sum(counts.values()) == 600
