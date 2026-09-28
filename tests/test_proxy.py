"""Guard core and FastAPI app with a fixture reply and deterministic detectors only."""

from pathlib import Path

from fastapi.testclient import TestClient

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.proxy.app import create_app
from socareguard.proxy.core import Guard

NOTE = "Client Tan Wei Ming, NRIC S1234567D, age 15, of Oakcrest Secondary School, case YC/2026/0412. Mother Mdm Lim Siew Lan (9123 4567)."


def make_guard(tmp_path: Path) -> Guard:
    return Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
    )


def test_guard_run_with_fixture(tmp_path):
    g = make_guard(tmp_path)
    res = g.run(
        [{"role": "user", "content": "Summarise.\n\n" + NOTE}],
        "youth-offending",
        "openai/gpt-4.1-mini",
        reply_fixture="PLACEHOLDER",
        seed=1,
    )
    kinds = [e.kind for e in res.events]
    assert (
        kinds[:3] == ["detect", "generalise", "substitute"]
        and "send" in kinds
        and "ledger" in kinds
    )
    send = next(e for e in res.events if e.kind == "send")
    for secret in ("S1234567D", "YC/2026/0412", "Oakcrest", "9123 4567"):
        assert secret not in send.outbound_text
    assert "a secondary school" in send.outbound_text
    row = res.ledger_row
    assert (
        row["transfer_basis"] and row["n_identifiers_substituted"] >= 3 and row["leakcheck_passed"]
    )
    assert g.ledger.verify()[0]


def test_guard_restores_surrogates_in_reply(tmp_path):
    g = make_guard(tmp_path)
    msgs = [{"role": "user", "content": NOTE}]
    _out_msgs, _, _, _, payload, _, _ = g.outbound(msgs, "youth-offending", "s1", seed=2)
    # a reply that echoes the pseudonymised payload should come back fully re-identified
    res = g.run(
        msgs,
        "youth-offending",
        "openai/gpt-4.1-mini",
        session="s1",
        reply_fixture="Summary: " + payload,
        seed=2,
    )
    assert (
        "S1234567D" in res.reply
        and "YC/2026/0412" in res.reply
        and "Oakcrest Secondary School" in res.reply
    )
    assert res.decision == "pass"


def test_app_endpoints(tmp_path, monkeypatch):
    g = make_guard(tmp_path)
    monkeypatch.setattr(
        "socareguard.proxy.core.complete",
        lambda model, messages, **kw: ("Draft OK", {"prompt_tokens": 1, "completion_tokens": 1}),
    )
    client = TestClient(create_app(g))
    assert client.get("/healthz").json()["ok"]
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": NOTE}]},
        headers={"X-SoCareGuard-Pack": "youth-offending"},
    )
    body = r.json()
    assert r.status_code == 200 and body["choices"][0]["message"]["content"] == "Draft OK"
    sg = body["socareguard"]
    assert sg["decision"] == "pass" and any(e["kind"] == "ledger" for e in sg["events"])
    tok = {"X-SoCareGuard-Session-Token": sg["session_token"]}
    ov = client.post(
        "/v1/override",
        headers=tok,
        json={
            "session": sg["session"],
            "pack": "youth-offending",
            "by": "worker",
            "flag_labels": ["OVER_CAUTION"],
            "reason": "",
        },
    )
    assert ov.status_code == 400
    ov = client.post(
        "/v1/override",
        headers=tok,
        json={
            "session": sg["session"],
            "pack": "youth-offending",
            "by": "worker",
            "flag_labels": ["OVER_CAUTION"],
            "reason": "client asked",
        },
    )
    # nothing was flagged on this session, so there is nothing to override
    assert ov.status_code == 400 and "raised on this session" in ov.json()["error"]["message"]
    v = client.get("/v1/ledger/verify").json()
    assert v["ok"] and v["rows"] == 1 and v["first_bad_row"] is None
    assert client.get("/v1/models").json()["data"][0]["object"] == "model"
    assert client.get(f"/v1/ledger?session={sg['session']}", headers=tok).json()["total"] == 1
    assert "error" in client.post("/v1/override", json={}).json()
    assert client.get(f"/v1/sessions/{sg['session']}").status_code == 403
    assert client.get(f"/v1/sessions/{sg['session']}", headers=tok).status_code == 200
    assert (
        client.post("/v1/chat/completions", json={"messages": [], "stream": True}).status_code
        == 400
    )


def test_panel_page_and_replacements(tmp_path, monkeypatch):
    g = make_guard(tmp_path)
    monkeypatch.setattr(
        "socareguard.proxy.core.complete", lambda model, messages, **kw: ("Draft OK", {})
    )
    client = TestClient(create_app(g))
    page = client.get("/")
    assert (
        page.status_code == 200
        and "What left the premises" in page.text
        and "uc1-youth-offending" in page.text
    )
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Summarise.\n\n" + NOTE}]},
        headers={"X-SoCareGuard-Pack": "youth-offending"},
    )
    sg = r.json()["socareguard"]
    assert "replacements" not in client.get(f"/v1/sessions/{sg['session']}/panel").json()
    panel = client.get(
        f"/v1/sessions/{sg['session']}/panel",
        headers={"X-SoCareGuard-Session-Token": sg["session_token"]},
    ).json()
    cats = {x["category"] for x in panel["replacements"]}
    assert {"NRIC", "CASE_REF", "SCHOOL"} <= cats
    assert all(x["original"] != x["outbound"] for x in panel["replacements"] if x["kind"] != "kept")


def test_rate_limit(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    g = make_guard(tmp_path)
    monkeypatch.setattr(
        "socareguard.proxy.core.complete", lambda model, messages, **kw: ("Draft OK", {})
    )
    monkeypatch.setattr(appmod, "MAX_PER_HOUR", 2)
    client = TestClient(appmod.create_app(g))
    codes = [
        client.post(
            "/v1/chat/completions", json={"messages": [{"role": "user", "content": NOTE}]}
        ).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]


def test_instruction_line_is_never_generalised(tmp_path):
    g = make_guard(tmp_path)
    msgs = [
        {
            "role": "user",
            "content": "Summarise this note and draft three next steps for the probation review.\n\n"
            + NOTE
            + " He is on probation.",
        }
    ]
    _out, _e, _k, _h, payload, _s, _r = g.outbound(msgs, "youth-offending", "s9", seed=3)
    assert payload.startswith(
        "Summarise this note and draft three next steps for the probation review."
    )
    assert "S1234567D" not in payload
    # one surrogate factory for the whole message: no two originals share a surrogate
    maps = [m for m in g.vault.mappings("s9") if m.kind == "surrogate"]
    assert len({m.surrogate for m in maps}) == len(maps)


def test_replacement_map_is_per_request_and_all_roles_are_sanitised(tmp_path: Path):
    g = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=None,
    )
    a = g.run(
        [{"role": "user", "content": "Summarise.\n\nNRIC S1234567D, phone 91234567."}],
        "youth-offending",
        "openai/gpt-4.1-mini",
        reply_fixture="ok",
        seed=1,
    )
    b = g.run(
        [
            {"role": "user", "content": "Log this."},
            {"role": "assistant", "content": "On file: NRIC S7654321A."},
            {"role": "user", "content": "Repeat the NRIC."},
        ],
        "youth-offending",
        "openai/gpt-4.1-mini",
        reply_fixture="ok",
        seed=2,
    )
    assert {r["original"] for r in a.replacements} == {"S1234567D", "91234567"}
    assert {r["original"] for r in b.replacements} == {"S7654321A"}
    assert all("S7654321A" not in m["content"] for m in b.outbound_messages)
    assert a.ledger_row["recipients"][0]["role"] == "drafting model"


def test_escalation_withholds_the_draft(tmp_path: Path):
    from socareguard.scenarios.events import Flag

    class Esc:
        def screen(self, draft, pack, seq, instruction="", leaks=None, context="", **kw):
            from socareguard.scenarios.events import Screen

            f = Flag(label="I14", clause="B.3.a", severity="escalate", evidence=draft[:20])
            return [f], "escalate", [Screen(seq=seq, flags=[f])]

    g = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=Esc(),
    )
    res = g.run(
        [{"role": "user", "content": "Email the school.\n\nNRIC S1234567D was charged."}],
        "youth-offending",
        "openai/gpt-4.1-mini",
        reply_fixture="Dear principal, S1234567D was charged.",
        seed=3,
    )
    assert res.withheld and "withheld" in res.reply and "S1234567D" not in res.reply
    assert "S1234567D" in res.reply_withheld and res.ledger_row["withheld"] is True


def test_integration_snippet_uses_forwarded_scheme(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    client = TestClient(appmod.create_app(make_guard(tmp_path)))
    fwd = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "demo.example.org"}
    monkeypatch.setattr(appmod, "TRUST_PROXY", False)
    assert 'base_url="http://testserver/v1"' in client.get("/", headers=fwd).text
    monkeypatch.setattr(appmod, "TRUST_PROXY", True)
    assert 'base_url="https://demo.example.org/v1"' in client.get("/", headers=fwd).text
    page = client.get("/", headers={"X-Forwarded-Proto": "https"}).text
    assert 'base_url="https://testserver/v1"' in page


def test_sandbox_banner_states_the_taxonomy_is_a_draft(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    monkeypatch.setattr(appmod, "SANDBOX", True)
    page = TestClient(appmod.create_app(make_guard(tmp_path))).get("/").text
    assert "not yet been reviewed by social-work practitioners" in page


def test_sandbox_release_of_a_withheld_draft_needs_the_session_token(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod
    from socareguard.scenarios.events import Flag, Screen

    class Esc:
        def screen(self, draft, pack, seq, instruction="", leaks=None, context="", **kw):
            f = Flag(label="I14", clause="B.3.a", severity="escalate", evidence=draft[:20])
            return [f], "escalate", [Screen(seq=seq, flags=[f])]

    g = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=Esc(),
    )
    monkeypatch.setattr(
        "socareguard.proxy.core.complete",
        lambda model, messages, **kw: ("Dear principal, the client was charged.", {}),
    )
    monkeypatch.setattr(appmod, "API_KEYS", set())
    client = TestClient(appmod.create_app(g))
    sg = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Email the school.\n\n" + NOTE}]},
        headers={"X-SoCareGuard-Pack": "youth-offending"},
    ).json()["socareguard"]
    assert sg["withheld"]
    url = f"/v1/sessions/{sg['session']}/withheld?reason=safeguarding%20review"
    role = {"X-SoCareGuard-Role": "supervisor"}
    assert client.get(url, headers=role).status_code == 403
    wrong = {**role, "X-SoCareGuard-Session-Token": "not-the-token"}
    assert client.get(url, headers=wrong).status_code == 403
    tok = {**role, "X-SoCareGuard-Session-Token": sg["session_token"]}
    r = client.get(url, headers=tok)
    assert r.status_code == 200 and r.json()["ledger_row"]["decision"] == "withheld_released"
    assert "self-asserted" in r.json()["ledger_row"]["actor"]
    no_role = {"X-SoCareGuard-Session-Token": sg["session_token"]}
    assert client.get(url, headers=no_role).status_code == 403
