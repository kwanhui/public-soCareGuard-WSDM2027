"""Use Case 2 against the paper's account (2026-10-20, night).

A link check saw one live replay of Use Case 2 raise I1 and annotate, as the paper and the
demonstration video show, and another raise I1 and I6 and escalate. Local replays found the judge's
input the same in every run, so the I6 flag is the judge's own variation and the screen is left as
evaluated. These tests hold that account: the replay gives the judge the same recorded note and
instruction every time, the threshold and the decision rule for I6 are those of the evaluation, and
the scenario card states the recorded verdict and that live flags can differ.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.policy.loader import load_pack
from socareguard.proxy.core import Guard
from socareguard.scenarios.authoring import uc2
from socareguard.screen.judge import FakeJudge, JudgeFlag
from socareguard.screen.screener import Screener

ROOT = Path(__file__).resolve().parent.parent
UC2 = ROOT / "demo/sample-inputs/scenarios/uc2-domestic-violence.jsonl"


def _events():
    return [json.loads(x) for x in UC2.read_text().splitlines() if x.strip()]


def _client(tmp_path, monkeypatch, judge):
    from socareguard.proxy import app as appmod

    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(appmod, "API_KEYS", set())
    monkeypatch.setattr(appmod, "SUPERVISOR_KEYS", set())
    monkeypatch.setattr(appmod, "SANDBOX", True)
    monkeypatch.setattr(
        "socareguard.proxy.core.complete",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("a replay calls no provider")),
    )
    guard = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=Screener(judge=judge, use_baseline=False),
    )
    return TestClient(appmod.create_app(guard))


def _replay(client):
    turn = _events()[1]
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "openai/gpt-4.1-mini",
            "messages": [{"role": "user", "content": turn["instruction"] + "\n\n" + turn["note"]}],
            "replay_scenario": "uc2-domestic-violence",
        },
        headers={"X-SoCareGuard-Pack": "domestic-violence"},
    )
    assert r.status_code == 200, r.text
    return r.json()["socareguard"]


def test_a_uc2_replay_gives_the_judge_the_same_input_every_time(tmp_path, monkeypatch):
    judge = FakeJudge()
    client = _client(tmp_path, monkeypatch, judge)
    _replay(client)
    _replay(client)
    recorded_note = next(e for e in _events() if e["kind"] == "send")["outbound_text"]
    reply = next(e for e in _events() if e["kind"] == "receive")["text"]
    assert len(judge.calls) == 2
    for call in judge.calls:
        assert call["context"] == recorded_note
        assert call["draft"] == reply
        assert call["instruction"] == _events()[1]["instruction"]
        # no closure hint is sent for this draft, so nothing outside the prompt varies
        assert call["hints"] == []
    assert judge.calls[0] == judge.calls[1]


def test_i6_escalates_at_the_evaluated_threshold_and_not_below_it():
    pack = load_pack("domestic-violence")
    assert pack.action_for("I6") == "escalate" and pack.action_for("I1") == "annotate"
    i1 = JudgeFlag("I1", "it is concerning", 0.95, "rewrite", "r")
    for conf, decision in ((0.7, "escalate"), (0.5, "escalate"), (0.49, "annotate")):
        judge = FakeJudge({"Case Summary": [i1, JudgeFlag("I6", "e", conf, None, "r")]})
        flags, got, _ = Screener(judge=judge, use_baseline=False).screen(
            "**Case Summary** it is concerning", pack, 1, instruction="Write a case summary."
        )
        assert got == decision, (conf, got)
        assert ("I6" in {f.label for f in flags}) == (conf >= 0.5)


def test_uc2_states_the_recorded_verdict_as_a_reference():
    head = _events()[0]
    ref = head["recorded_screen"]
    assert ref["recorded_on"] == "2026-09-28" and ref["decision"] == "annotate"
    assert [(f["label"], f["clause"], f["confidence"]) for f in ref["flags"]] == [
        ("I1", "A.7.c", 0.95)
    ]
    assert "space-2026-09-28-2" in ref["what"] and "video" in ref["source"]
    summary = head["summary"]
    assert "In the recorded demonstration of 2026-09-28" in summary
    assert "can differ between runs" in summary and "I6" in summary and "escalates" in summary
    assert "The screener flags SASW A.7.c" not in summary
    # the authored script and the shipped script carry the same header
    authored = json.loads(uc2()[0])
    assert authored["summary"] == summary and authored["recorded_screen"] == ref
    assert summary in (ROOT / "demo/scenarios.md").read_text()


def test_the_panel_lists_the_uc2_reference_and_names_added_flags(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    monkeypatch.chdir(ROOT)
    scen = next(s for s in appmod.load_scenarios() if s["id"] == "uc2-domestic-violence")
    assert scen["recorded_screen"]["flags"][0]["label"] == "I1"
    js = (ROOT / "src/socareguard/proxy/static/panel.js").read_text()
    assert "this run also raised" in js and "this run did not raise" in js
