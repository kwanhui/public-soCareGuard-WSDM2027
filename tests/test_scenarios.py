from pathlib import Path

import yaml

from socareguard.scenarios import replay
from socareguard.scenarios.authoring import SCENARIOS, build

SCEN_DIR = Path("demo/sample-inputs/scenarios")


def test_build_matches_committed_structure(tmp_path):
    """The committed scripts carry live recordings, so only the event skeleton must match the authoring source."""
    built = build(tmp_path)
    assert len(built) == 4
    for p in built:
        committed = SCEN_DIR / p.name
        assert committed.exists(), (
            f"{committed} missing; run python3 -m socareguard.scenarios build"
        )
        skel = lambda path: [(e.kind, getattr(e, "seq", 0)) for e in replay.load(path)]
        assert skel(committed) == skel(p), f"{committed} event skeleton differs from authoring.py"
        rec = next(e for e in replay.load(committed) if e.kind == "receive")
        assert rec.source in ("recorded", "authored")


def test_scenarios_validate():
    for name in SCENARIOS:
        assert replay.validate(SCEN_DIR / f"{name}.jsonl") == []


def test_storyboard_replay_has_no_failures():
    for name in SCENARIOS:
        res = replay.run(SCEN_DIR / f"{name}.jsonl")
        assert res["summary"]["fail"] == 0, res
        # before the proxy exists, checks on pipeline events are pending, not passing
        assert res["summary"]["pending"] >= 1


def test_scenario_raw_notes_carry_valid_identifiers():
    import re

    from socareguard.corpus.identifiers import is_valid_nric

    for name in SCENARIOS:
        events = replay.load(SCEN_DIR / f"{name}.jsonl")
        note = next(e.note for e in events if e.kind == "user_turn")
        for m in re.findall(r"\b[STFGM]\d{7}[A-Z]\b", note):
            assert is_valid_nric(m), m


def test_policy_packs_reference_known_categories():
    from socareguard.taxonomy import BY_ID

    for p in Path("policy-packs").glob("*.yaml"):
        pack = yaml.safe_load(p.read_text())
        assert pack["status"].startswith("draft")
        for c in pack["inbound"]["categories"]:
            assert c["id"] in BY_ID, (p, c)
            assert pack["id"] in BY_ID[c["id"]].packs
        assert pack["override"]["requires_reason"] is True
