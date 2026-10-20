"""Proxy behaviour changed after the 2026-09-28 review round 1: reasons without identifiers
(COMP-F3), overrides tied to the session's raised flags (COMP-F4), the panel map of a withheld
session (SUP-F1), repeated releases (SUP-F3), and the no-token message (WSDM-F10)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.proxy.core import Guard
from socareguard.scenarios.events import Flag, Screen

NOTE = "Client Tan Wei Ming, NRIC S1234567D, age 15, of Oakcrest Secondary School, case YC/2026/0412. Mother Mdm Lim Siew Lan (9123 4567)."
REPLY = "Dear principal, the young person was charged with theft last month."


class OneFlag:
    def __init__(self, label, severity):
        self.label, self.severity = label, severity

    def screen(self, draft, pack, seq, instruction="", leaks=None, context="", **kw):
        f = Flag(label=self.label, clause="A.7.c", severity=self.severity, evidence=draft[:20])
        return [f], self.severity, [Screen(seq=seq, flags=[f])]


def _client(tmp_path: Path, monkeypatch, label="I1", severity="annotate"):
    from socareguard.proxy import app as appmod

    g = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=OneFlag(label, severity),
    )
    monkeypatch.setattr(
        "socareguard.proxy.core.complete", lambda model, messages, **kw: (REPLY, {})
    )
    monkeypatch.setattr(appmod, "API_KEYS", set())
    client = TestClient(appmod.create_app(g))
    sg = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Email the school.\n\n" + NOTE}]},
        headers={"X-SoCareGuard-Pack": "youth-offending"},
    ).json()["socareguard"]
    return client, sg


def _override(client, sg, labels, reason):
    return client.post(
        "/v1/override",
        headers={"X-SoCareGuard-Session-Token": sg["session_token"]},
        json={
            "session": sg["session"],
            "pack": "youth-offending",
            "by": "sw-042",
            "flag_labels": labels,
            "reason": reason,
            "request_row_sha256": sg["ledger_row_sha256"],
            "draft_sha256": "ab" * 32,
        },
    )


@pytest.mark.parametrize(
    "reason",
    [
        "Client S1234567D asked for this wording",
        "confirmed with mother on 9123 4567",
        "per case YC/2026/0412 protocol",
    ],
)
def test_override_reason_with_an_identifier_is_refused(tmp_path, monkeypatch, reason):
    client, sg = _client(tmp_path, monkeypatch)
    r = _override(client, sg, ["I1"], reason)
    assert r.status_code == 400
    assert r.json()["error"]["message"].startswith("Reason must not contain an identifier")
    assert all(row.get("decision") != "override" for row in client.app.state.guard.ledger.rows())


def test_override_reason_without_an_identifier_is_recorded(tmp_path, monkeypatch):
    client, sg = _client(tmp_path, monkeypatch)
    r = _override(client, sg, ["I1"], "wording agreed at the case conference; risk language kept")
    assert r.status_code == 200 and r.json()["ledger_row"]["flags"] == ["I1"]


def test_override_must_name_a_flag_raised_on_the_session(tmp_path, monkeypatch):
    client, sg = _client(tmp_path, monkeypatch)
    r = _override(client, sg, ["I7"], "client asked")
    assert r.status_code == 400 and "not raised: I7" in r.json()["error"]["message"]
    assert _override(client, sg, [], "client asked").status_code == 400
    assert _override(client, sg, ["I1", "I7"], "client asked").status_code == 400


def test_no_session_token_says_so(tmp_path, monkeypatch):
    client, sg = _client(tmp_path, monkeypatch)
    for r in (
        client.get(f"/v1/ledger?session={sg['session']}"),
        client.post(
            "/v1/override",
            json={
                "session": sg["session"],
                "pack": "youth-offending",
                "flag_labels": ["I1"],
                "reason": "x",
            },
        ),
    ):
        assert r.status_code == 403 and r.json()["error"]["message"] == "Session token required"
    wrong = {"X-SoCareGuard-Session-Token": "not-the-token"}
    r = client.get(f"/v1/sessions/{sg['session']}", headers=wrong)
    assert r.status_code == 403 and "another client" in r.json()["error"]["message"]


def test_panel_map_of_a_withheld_session_carries_no_reply_text(tmp_path, monkeypatch):
    client, sg = _client(tmp_path, monkeypatch, "I14", "escalate")
    assert sg["withheld"]
    r = client.get(
        f"/v1/sessions/{sg['session']}/panel",
        headers={"X-SoCareGuard-Session-Token": sg["session_token"]},
    )
    body = r.json()
    assert r.status_code == 200 and set(body) == {"session", "replacements"}
    text = r.text
    assert "charged with theft" not in text and "Dear principal" not in text
    # the map decodes only what the practitioner typed
    typed = "Email the school.\n\n" + NOTE
    assert all(m["original"] in typed for m in body["replacements"] if m["kind"] != "derived")


def _sign_in(client):
    """The sandbox login: the only way to release a withheld draft without supervisor keys."""
    r = client.post(
        "/supervisor/login",
        data={"username": "admin", "password": "demo1234"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_withheld_release_refuses_a_reason_with_an_identifier(tmp_path, monkeypatch):
    client, sg = _client(tmp_path, monkeypatch, "I14", "escalate")
    _sign_in(client)
    h = {"X-SoCareGuard-Session-Token": sg["session_token"]}
    r = client.get(
        f"/v1/sessions/{sg['session']}/withheld?reason=released%20for%20S1234567D", headers=h
    )
    assert r.status_code == 400 and "identifier" in r.json()["error"]["message"]


def test_second_release_links_the_earlier_release(tmp_path, monkeypatch):
    client, sg = _client(tmp_path, monkeypatch, "I14", "escalate")
    url = f"/v1/sessions/{sg['session']}/withheld?reason=safeguarding%20review"
    _sign_in(client)
    tok = {"X-SoCareGuard-Session-Token": sg["session_token"]}
    first = client.get(url, headers=tok).json()
    assert first["prior_releases"] == [] and first["ledger_row"]["prior_release_row_sha256"] is None
    second = client.get(url, headers=tok).json()
    prior = second["prior_releases"]
    assert len(prior) == 1 and prior[0]["actor"] == "admin (sandbox login)"
    assert prior[0]["row_sha256"] == first["ledger_row"]["row_sha256"]
    assert second["ledger_row"]["prior_release_row_sha256"] == [first["ledger_row"]["row_sha256"]]


def test_panel_page_carries_the_review_round_wording(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    monkeypatch.setattr(appmod, "SANDBOX", True)
    client, _ = _client(tmp_path, monkeypatch)
    page = client.get("/").text
    # round 6 (first-time user): the Recipient hint names no flag code; the codes sit in its "More"
    assert "Who the draft is for. Some flags depend on it." in page
    assert "In the sandbox the supervisor id is typed in and not checked." not in page
    assert "outside the host is the deployer's step" in page
    assert '"I1": {"precision": 0.45' in page
    js = client.get("/static/panel.js").text
    for s in (
        "Draft taxonomy, not yet practitioner-reviewed",
        "measured precision on synthetic drafts",
        "Give the session id to your supervisor, who signs in at the supervisor view",
        "Released earlier by",
        '"typed in"',
        '"checked by a person"',
        "`${base} (${how})`",
    ):
        assert s in js, s
