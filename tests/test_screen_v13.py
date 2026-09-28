"""The screen evaluation on corpus v1.3 (round 6): the loader appends the 30 care-team drafts to
the 690 drafts of v1.2, the recipient kinds come from the v1.2 and v1.3 files, the gate report has
three tiers, and the tier-off comparison judges a care-team draft with the plain prompt."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from socareguard.eval import run_screen
from socareguard.eval.report import _gate_table
from socareguard.screen.judge import FakeJudge

ROOT = Path(__file__).parent.parent
PACKS = ("disability", "domestic-violence", "youth-offending")


@pytest.fixture(autouse=True)
def _in_repo(monkeypatch):
    monkeypatch.chdir(ROOT)


def test_v13_loader_counts_600_plus_90_plus_30():
    v11 = run_screen.load_screen_drafts(PACKS, corpus="v1.1")
    v12 = run_screen.load_screen_drafts(PACKS, corpus="v1.2")
    v13 = run_screen.load_screen_drafts(PACKS, corpus="v1.3")
    assert (len(v11), len(v12), len(v13)) == (600, 690, 720)
    assert [d.id for d in v13 if d.id in {x.id for x in v12}] == [d.id for d in v12]
    added = [d for d in v13 if d.id not in {x.id for x in v12}]
    assert len(added) == 30 and all(d.label.value == "NONE" for d in added)
    assert {d.audience for d in added} == {"care-team"}
    assert len({d.id for d in v13}) == 720
    with pytest.raises(ValueError):
        run_screen.load_screen_drafts(PACKS, corpus="v1.4")


def test_recipient_kinds_cover_the_v12_and_v13_files():
    kinds = run_screen._recipient_kinds()
    care = sorted(k for k, v in kinds.items() if v == "care-team")
    assert len(kinds) == 120
    assert len(care) == 33
    assert sum(1 for k in care if "-ext-" in k) == 3
    assert sum(1 for k in care if "-ct-" in k) == 30
    drafts = run_screen.load_screen_drafts(PACKS, corpus="v1.3")
    # the tier of each compliant draft; a failure draft's tier follows its instruction
    tiers = [run_screen.draft_audience(d, kinds)[0] for d in drafts if d.label.value == "NONE"]
    assert (tiers.count("internal"), tiers.count("care-team"), tiers.count("external")) == (
        300,
        33,
        87,
    )


def test_added_ids_are_dropped_by_the_rescore():
    ids = run_screen.added_draft_ids()
    assert len(ids) == 120
    v11 = {d.id for d in run_screen.load_screen_drafts(PACKS, corpus="v1.1")}
    assert not ids & v11


def _row(label, flags, audience=None, kind=None, task="summary_plan"):
    r = {"draft": "x", "pack": "disability", "task": task, "label": label,
         "judge_flags": flags, "rule_over_caution": False, "baseline": None}  # fmt: skip
    if audience:
        r["audience"] = audience
    if kind:
        r["recipient_kind"] = kind
    return r


def test_three_tier_report_from_v13_rows():
    rows = [
        _row("I1", {"I1": 0.9}),
        _row("NONE", {"I10": 0.9}),  # internal: the gate removes I10
        _row("NONE", {}),
        _row("NONE", {"I10": 0.9}, "care-team", "care-team", "dac_support_note"),
        _row("NONE", {}, "care-team", "care-team", "shelter_note"),
        _row("NONE", {}, "care-team", "care-team", "cocase_note"),
        _row("NONE", {"I14": 1.0}, "external", "care-team", "school_letter"),
        _row("NONE", {"I10": 0.95}, "external", "external", "referral_note"),
    ]
    res = run_screen.summarise(rows, "j", "t", use_baseline=False)
    by = res["binary"]["compliant_by_audience"]
    assert list(by) == ["internal", "care-team", "external"]
    assert by["internal"] == {"compliant_drafts": 2, "fpr_gated": 0.0, "fpr_ungated": 0.5}
    assert by["care-team"] == {"compliant_drafts": 4, "fpr_gated": 0.5, "fpr_ungated": 0.5}
    assert by["external"] == {"compliant_drafts": 1, "fpr_gated": 1.0, "fpr_ungated": 1.0}
    table = _gate_table({**res, "corpus": "v1.3", "tag": "none"}, None)
    assert "Care-team compliant, gated" in table[0] and "Other external compliant" in table[0]
    assert "0.500 (n=4)" in table[2] and "1.000 (n=1)" in table[2]
    assert any("draft reading of SASW A.6.d" in line for line in table)


def test_tier_off_judges_a_care_team_draft_with_the_plain_prompt():
    kinds = run_screen._recipient_kinds()
    d = next(
        x
        for x in run_screen.load_screen_drafts(PACKS, corpus="v1.3")
        if x.id == "disability-010-ct-dac_support_note"
    )
    on, off = FakeJudge(), FakeJudge()
    row_on = run_screen.judge_one(d, on, False, "", kinds)
    row_off = run_screen.judge_one(d, off, False, "", kinds, tier_off=True)
    assert on.calls[0]["audience"] == "care-team" and on.calls[0]["care_team_kind"]
    assert off.calls[0]["audience"] is None and off.calls[0]["care_team_kind"] is None
    assert row_off["tier_off"] is True and "tier_off" not in row_on
    assert row_on["recipient_kind"] == row_off["recipient_kind"] == "care-team"
    assert row_off["prompt_sha256"] == run_screen.prompt_sha256(d, "", False)
    assert row_on["prompt_sha256"] != row_off["prompt_sha256"]


def test_v13_reuse_copies_every_v12_row_except_the_care_team_drafts():
    if not (ROOT / "docs/metrics/screen-v1.2-rows.jsonl").exists():
        pytest.skip("no v1.2 rows")
    drafts = run_screen.load_screen_drafts(PACKS, None, "v1.3")
    kinds = run_screen._recipient_kinds()
    plan = run_screen.reuse_plan(drafts, "v1.2", False, run_screen._notes(PACKS), kinds)
    judged = [d.id for d in drafts if d.id not in plan]
    assert len(plan) == 687 and len(judged) == 33
    assert {i for i in judged} == {k for k, v in kinds.items() if v == "care-team"}


def test_v13_rescore_equals_v12_on_the_600_drafts():
    a, b = (ROOT / "docs/metrics" / f"screen-{t}-v1.1-drafts.json" for t in ("v1.2", "v1.3"))
    if not (a.exists() and b.exists()):
        pytest.skip("no rescored files")
    v12, v13 = json.loads(a.read_text()), json.loads(b.read_text())
    assert v13["drafts"] == 600
    for k in ("precision", "recall", "f1", "fpr", "auprc"):
        assert v12["binary"][k] == v13["binary"][k]
    assert v12["threshold_sweep"] == v13["threshold_sweep"]
    for lab, v in v12["per_label"].items():
        assert {k: x for k, x in v.items() if "deprecated" not in k} == {
            k: x for k, x in v13["per_label"][lab].items() if "deprecated" not in k
        }
