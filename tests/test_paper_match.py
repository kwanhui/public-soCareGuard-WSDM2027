"""The sandbox against the WSDM 2027 paper's account (2026-10-20).

The judge is a provider outside the premises, so it reads the instruction with stand-ins. A
replayed reply is screened against the note that its model was given when it was recorded. Use
Case 4 keeps a recording from each provider, and the panel replays either. Only a signed-in
supervisor releases a withheld draft. The pack and the chain check have pages with a way back
to the panel, and the JSON routes are unchanged. The banner names the paper's decision.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.proxy.core import Guard
from socareguard.screen.judge import FakeJudge, JudgeFlag
from socareguard.screen.screener import Screener

ROOT = Path(__file__).resolve().parent.parent
SCEN = ROOT / "demo/sample-inputs/scenarios"
NOTE = "Client Tan Wei Ming, NRIC S1234567D, case YC/2026/0412, at Oakcrest Secondary School."


def _guard(tmp_path, judge):
    return Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=Screener(judge=judge, use_baseline=False),
    )


def _app(tmp_path, monkeypatch, judge=None):
    from socareguard.proxy import app as appmod

    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(appmod, "API_KEYS", set())
    monkeypatch.setattr(appmod, "SUPERVISOR_KEYS", set())
    monkeypatch.setattr(appmod, "SANDBOX", True)
    monkeypatch.setattr(
        "socareguard.proxy.core.complete",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("a replay calls no provider")),
    )
    judge = judge or FakeJudge()
    return TestClient(appmod.create_app(_guard(tmp_path, judge))), judge


def _scenario(name):
    return [json.loads(x) for x in (SCEN / f"{name}.jsonl").read_text().splitlines() if x.strip()]


# ---------- the screen ----------


def test_the_judge_reads_the_instruction_with_stand_ins(tmp_path):
    judge = FakeJudge()
    g = _guard(tmp_path, judge)
    g.run(
        [{"role": "user", "content": "Write to the school about S1234567D.\n\n" + NOTE}],
        "youth-offending",
        "openai/gpt-4.1-mini",
        reply_fixture="ok",
        seed=1,
    )
    call = judge.calls[0]
    # the NRIC is found by the deterministic layer, so this runs without the NER models
    assert "S1234567D" not in call["instruction"] and "school" in call["instruction"]
    assert "S1234567D" not in call["context"]


def test_a_replay_is_screened_against_the_note_its_model_was_given(tmp_path):
    judge = FakeJudge()
    g = _guard(tmp_path, judge)
    recorded_note = "Draft a note to an employer.\n\nClient Lee, 29, attends a day centre."
    res = g.run(
        [{"role": "user", "content": "Draft a note to the cafe.\n\n" + NOTE}],
        "disability",
        "openai/gpt-4.1-mini",
        reply_fixture="Dear supervisor, Lee is 29.",
        reply_fixture_note=recorded_note,
        seed=1,
    )
    assert judge.calls[0]["context"] == recorded_note
    # the practitioner's instruction is still the one typed in this request, with stand-ins
    assert judge.calls[0]["instruction"] == "Draft a note to the cafe."
    screen = next(e for e in res.events if e.kind == "screen")
    assert screen.note_source == "recorded"
    # what left the premises is this request's own outbound text
    send = next(e for e in res.events if e.kind == "send")
    assert "Draft a note to the cafe." in send.outbound_text


def test_a_live_request_is_screened_against_its_own_outbound_text(tmp_path):
    judge = FakeJudge()
    g = _guard(tmp_path, judge)
    res = g.run(
        [{"role": "user", "content": "Summarise.\n\n" + NOTE}],
        "youth-offending",
        "openai/gpt-4.1-mini",
        reply_fixture="ok",
        seed=1,
    )
    send = next(e for e in res.events if e.kind == "send")
    assert judge.calls[0]["context"] == send.outbound_text
    assert next(e for e in res.events if e.kind == "screen").note_source == "live"


# ---------- Use Case 3 and Use Case 4 ----------


def test_uc3_states_the_recorded_verdict_as_a_reference():
    head = _scenario("uc3-disability")[0]
    ref = head["recorded_screen"]
    assert ref["recorded_on"] == "2026-09-28" and ref["decision"] == "annotate"
    assert [f["label"] for f in ref["flags"]] == ["I10", "I3"]
    assert "In the recorded demonstration of 2026-09-28" in head["summary"]
    assert "can differ between runs" in head["summary"]
    assert "the screener flags I10" not in head["summary"]


def test_uc4_keeps_one_recording_per_provider():
    events = _scenario("uc4-over-caution-override")
    recs = [e for e in events if e["kind"] == "receive"]
    assert [(r["model"], r["recorded_at"][:10]) for r in recs] == [
        ("openai/gpt-4.1-mini", "2026-09-07"),
        ("anthropic/claude-sonnet-5", "2026-10-20"),
    ]
    assert all(r["source"] == "recorded" for r in recs)
    sends = [e for e in events if e["kind"] == "send"]
    assert len(sends) == 2 and sends[1]["provider"] == "anthropic"
    assert sends[0]["payload_sha256"] == sends[1]["payload_sha256"]
    # the card says what each recording shows, not that both providers did the same here
    summary = events[0]["summary"]
    assert "Both providers did this" not in summary and "2026-10-20" in summary


def test_the_panel_replays_either_uc4_recording(tmp_path, monkeypatch):
    judge = FakeJudge(
        {"self-harm": [JudgeFlag("I10", "history of self-harm", 0.9, "Please book Room 3.", "r")]}
    )
    client, judge = _app(tmp_path, monkeypatch, judge)
    scen = next(
        s
        for s in json.loads(
            re.search(r"window\.SCENARIOS = (.*?); window\.TAXONOMY", client.get("/").text).group(1)
        )
        if s["id"] == "uc4-over-caution-override"
    )
    assert scen["recordings"] == [
        {"model": "openai/gpt-4.1-mini", "recorded_on": "2026-09-07"},
        {"model": "anthropic/claude-sonnet-5", "recorded_on": "2026-10-20"},
    ]
    turn = _scenario("uc4-over-caution-override")[1]
    msgs = [{"role": "user", "content": turn["instruction"] + "\n\n" + turn["note"]}]
    seen = {}
    for model in ("openai/gpt-4.1-mini", "anthropic/claude-sonnet-5"):
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "openai/gpt-4.1-mini",
                "messages": msgs,
                "replay_scenario": "uc4-over-caution-override",
                "replay_model": model,
            },
            headers={"X-SoCareGuard-Pack": "disability"},
        )
        assert r.status_code == 200, r.text
        sg = r.json()["socareguard"]
        assert sg["replayed"] and sg["recording"]["model"] == model
        assert sg["ledger_row"]["model"] == model and sg["ledger_row"]["replayed_reply"]
        recv = next(e for e in sg["events"] if e["kind"] == "receive")
        seen[model] = recv["text"]
        assert next(e for e in sg["events"] if e["kind"] == "screen")["note_source"] == "recorded"
    assert seen["openai/gpt-4.1-mini"] != seen["anthropic/claude-sonnet-5"]
    assert "self-harm" in seen["openai/gpt-4.1-mini"]
    bad = client.post(
        "/v1/chat/completions",
        json={
            "messages": msgs,
            "replay_scenario": "uc4-over-caution-override",
            "replay_model": "openai/gpt-5",
        },
        headers={"X-SoCareGuard-Pack": "disability"},
    )
    assert bad.status_code == 400


# ---------- the release ----------


def test_the_practitioner_panel_has_no_release(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    js = client.get("/static/panel.js").text
    assert '$("release").hidden = true;' in js
    assert 'id="escalate-supervisor-link"' in js and "There is no release on this panel." in js
    assert "X-SoCareGuard-Role" not in js
    # the review page still offers it to a signed-in supervisor
    assert '$("release").hidden = !canRelease;' in js
    page = client.get("/").text
    assert "typed in and not checked" not in page


# ---------- pages for a browser, JSON for an application ----------


def test_the_pack_page_shows_the_yaml_with_a_way_back(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    r = client.get("/packs/disability")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    text = r.text
    assert 'href="/"' in text and 'href="/v1/packs/disability"' in text
    yaml_text = (ROOT / "policy-packs/disability.yaml").read_text()
    first = next(x for x in yaml_text.splitlines() if x.strip() and not x.startswith("#"))
    assert first.split(":")[0] in text and "YAML" in text
    assert client.get("/packs/nonsense").status_code == 404
    assert client.get("/packs", follow_redirects=False).status_code == 303
    j = client.get("/v1/packs/disability")
    assert j.headers["content-type"].startswith("application/json") and j.json()["id"]
    assert client.get("/v1/packs").json()["packs"]


def test_the_chain_page_has_a_way_back_and_the_json_route_is_unchanged(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    r = client.get("/ledger/check", headers={"Accept": "text/html"})
    assert r.status_code == 200 and 'href="/"' in r.text and 'href="/v1/ledger/verify"' in r.text
    assert "chain intact over" in r.text
    j = client.get("/v1/ledger/verify", headers={"Accept": "text/html"})
    assert j.headers["content-type"].startswith("application/json")
    assert j.json()["ok"] is True and j.json()["message"].startswith("chain intact over")


def test_the_footer_links_the_pages_and_the_snippet_names_packs_and_replay(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    page = client.get("/").text
    assert 'href="/ledger/check"' in page and 'href="/packs/' in page
    assert "curl http://testserver/v1/packs" in page
    assert '"replay_scenario": "uc4-over-caution-override"' in page


# ---------- the paper's decision names ----------


def test_the_banner_names_the_papers_decision():
    js = (ROOT / "src/socareguard/proxy/static/panel.js").read_text()
    assert (
        'const DECISION_LABEL = {pass: "Pass", annotate: "Flagged (annotate)", '
        'regenerate: "Regenerate", escalate: "Escalate"};'
    ) in js
    assert "const label = DECISION_LABEL[sg.decision] || sg.decision;" in js
    assert 'regenerate: "regenerate: needs a new draft"' in js
