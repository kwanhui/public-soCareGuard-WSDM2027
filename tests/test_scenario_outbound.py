"""The shipped scenario notes, through the deterministic layer of the guard: what leaves must never
assert something the note does not. These are the notes behind the paper and the video."""

import json
from pathlib import Path

import pytest

from socareguard.outbound.sanitise import Sanitiser
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack

SCENARIOS = Path(__file__).resolve().parents[1] / "demo" / "sample-inputs" / "scenarios"

RULES = {
    "uc1-youth-offending": (
        ["Sec 3", "First contact"],
        ["prior record", "family member", "violenceing", "has a prior"],
    ),
    "uc2-domestic-violence": (["pending"], ["decided against", "is in place"]),
    "uc3-disability": (
        ["presumed", "Has capacity for this decision."],
        ["in question", "a an ", "held them"],
    ),
    "uc4-over-caution-override": ([], ["prior record", "a an "]),
}


@pytest.mark.parametrize("name", sorted(RULES))
def test_scenario_outbound_polarity(tmp_path: Path, name: str):
    lines = [
        json.loads(x) for x in (SCENARIOS / f"{name}.jsonl").read_text().splitlines() if x.strip()
    ]
    head = next(x for x in lines if x["kind"] == "scenario")
    turn = next(x for x in lines if x["kind"] == "user_turn")
    s = Sanitiser(
        Vault(tmp_path / "v.sqlite"), load_pack(head["pack"]), use_presidio=False, use_gliner=False
    )
    out = s.sanitise(turn["instruction"] + "\n\n" + turn["note"], session=name, seed=1).text
    must, must_not = RULES[name]
    for m in must:
        assert m in out, (name, m, out)
    for m in must_not:
        assert m not in out, (name, m, out)
