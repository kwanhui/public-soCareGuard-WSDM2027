"""The hosted sandbox's two spending limits (2026-10-20): 40 requests per hour from each address,
and a ceiling on the estimated model spend of the whole process per UTC day (USD 5 on the Space).
Past the ceiling a chat request is refused with HTTP 429 for everyone, and the pages that make no
model call (supervisor review and release, the record, the packs) keep working."""

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from tests.test_proxy import NOTE, make_guard
from tests.test_round6_supervisor import _app, _login, _release, _send

ROOT = Path(__file__).resolve().parent.parent
LIVE = 0.0057 + 0.0004  # the judge and the drafting call (docs/metrics.md, "Cost")
REPLAY = 0.0057  # the judge only


def _chat(client, replay=None):
    body = {"messages": [{"role": "user", "content": "Summarise.\n\n" + NOTE}]}
    headers = {"X-SoCareGuard-Pack": "youth-offending"}
    if replay:
        body["replay_scenario"] = replay
        headers["X-SoCareGuard-Pack"] = "disability"
    return client.post("/v1/chat/completions", json=body, headers=headers)


def test_the_space_image_sets_40_per_hour_and_usd_5_per_day():
    env = next(
        line for line in (ROOT / "Dockerfile").read_text().splitlines() if line.startswith("ENV PORT")
    )
    assert "SOCAREGUARD_MAX_REQUESTS_PER_HOUR=40" in env
    assert "SOCAREGUARD_DAILY_SPEND_USD=5" in env
    # The agency deploy shares the image, so it switches both limits off explicitly.
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    envs = compose["services"]["socareguard"]["environment"]
    assert envs["SOCAREGUARD_MAX_REQUESTS_PER_HOUR"] == "0"
    assert envs["SOCAREGUARD_DAILY_SPEND_USD"] == "0"


def test_no_doc_or_script_still_states_20_per_hour():
    stale = re.compile(r"20 (requests )?per hour|20/hour|PER_HOUR=20|sets 20\b")
    for rel in (
        "README.md",
        "demo/README.md",
        "Dockerfile",
        "src/socareguard/proxy/static/panel.js",
        "src/socareguard/proxy/templates/panel.html",
    ):
        assert not stale.search((ROOT / rel).read_text()), rel


def test_the_rate_limit_message_names_the_limit(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    monkeypatch.setattr(
        "socareguard.proxy.core.complete", lambda model, messages, **kw: ("Draft OK", {})
    )
    monkeypatch.setattr(appmod, "MAX_PER_HOUR", 1)
    client = TestClient(appmod.create_app(make_guard(tmp_path)))
    assert _chat(client).status_code == 200
    r = _chat(client)
    assert r.status_code == 429
    err = r.json()["error"]
    assert err["code"] == "rate_limit_exceeded"
    assert "1 requests per hour from each address" in err["message"]


def test_the_ceiling_refuses_chat_for_everyone_with_a_plain_message(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    monkeypatch.setattr(appmod, "DAILY_SPEND_USD", round(LIVE + REPLAY, 4))
    monkeypatch.setattr(appmod, "MAX_PER_HOUR", 0)
    client, g = _app(tmp_path, monkeypatch)
    assert _chat(client).status_code == 200  # live: judge and drafting
    assert _chat(client, replay="uc4-over-caution-override").status_code == 200  # judge only
    rows = len(g.ledger.rows())
    # A request from another address is refused as well: the ceiling is shared.
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Summarise.\n\n" + NOTE}]},
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert r.status_code == 429
    err = r.json()["error"]
    assert err["code"] == "daily_budget_exhausted"
    msg = err["message"]
    assert "daily model budget (USD 0.0118) is used up for everyone" in msg
    assert "not a per-person one" in msg
    assert "00:00 UTC (08:00 Singapore time)" in msg
    assert re.search(r"in \d+ h \d\d min", msg)
    assert _chat(client, replay="uc4-over-caution-override").status_code == 429
    assert len(g.ledger.rows()) == rows  # nothing ran, so nothing was recorded


def test_a_refusal_for_the_budget_does_not_use_up_the_address_limit(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    monkeypatch.setattr(appmod, "DAILY_SPEND_USD", LIVE)
    monkeypatch.setattr(appmod, "MAX_PER_HOUR", 2)
    client, _ = _app(tmp_path, monkeypatch)
    assert _chat(client).status_code == 200
    for _ in range(3):
        assert _chat(client).json()["error"]["code"] == "daily_budget_exhausted"
    assert len(client.app.state.limiter.hits["testclient"]) == 1


def test_the_tally_resets_at_utc_midnight(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    monkeypatch.setattr(appmod, "DAILY_SPEND_USD", LIVE)
    client, _ = _app(tmp_path, monkeypatch)
    meter = client.app.state.spend
    monkeypatch.setattr(appmod.SpendMeter, "_today", staticmethod(lambda: "2026-10-20"))
    assert _chat(client).status_code == 200
    assert _chat(client).status_code == 429
    monkeypatch.setattr(appmod.SpendMeter, "_today", staticmethod(lambda: "2026-10-21"))
    assert _chat(client).status_code == 200
    assert meter.day == "2026-10-21"


def test_supervisor_review_release_and_read_only_pages_work_past_the_ceiling(
    tmp_path, monkeypatch
):
    from socareguard.proxy import app as appmod

    monkeypatch.setattr(appmod, "DAILY_SPEND_USD", LIVE)
    client, g = _app(tmp_path, monkeypatch)
    sg = _send(client)  # youth-offending escalates in this test app, so the draft is withheld
    assert sg["withheld"]
    assert _chat(client).json()["error"]["code"] == "daily_budget_exhausted"
    _login(client)
    assert client.get("/supervisor").status_code == 200
    assert client.get("/v1/supervisor/summary").status_code == 200
    assert client.post(f"/v1/sessions/{sg['session']}/review-token").status_code == 200
    rel = _release(client, sg)
    assert rel.status_code == 200 and g.ledger.rows()[-1]["decision"] == "withheld_released"
    for url in ("/", "/healthz", "/packs", "/packs/disability", "/ledger/check", "/v1/ledger/verify"):
        assert client.get(url).status_code == 200, url


def test_healthz_reports_the_limits_and_no_secret(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    monkeypatch.setattr(appmod, "DAILY_SPEND_USD", 5.0)
    monkeypatch.setattr(appmod, "MAX_PER_HOUR", 40)
    client, _ = _app(tmp_path, monkeypatch)
    h = client.get("/healthz").json()
    assert h["max_requests_per_hour"] == 40
    assert h["daily_spend"]["ceiling_usd"] == 5.0
    assert h["daily_spend"]["spent_usd_estimate"] == 0 and h["daily_spend"]["ratio"] == 0
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT00:00:00Z", h["daily_spend"]["resets_at"])
    _chat(client)
    h = client.get("/healthz").json()
    assert h["daily_spend"]["spent_usd_estimate"] == pytest.approx(LIVE)
    assert h["daily_spend"]["ratio"] == pytest.approx(LIVE / 5, abs=1e-4)
    assert set(h) == {"ok", "packs", "sandbox", "max_requests_per_hour", "daily_spend"}


def test_no_ceiling_by_default():
    src = (ROOT / "src/socareguard/proxy/app.py").read_text()
    assert 'os.environ.get("SOCAREGUARD_DAILY_SPEND_USD", "0")' in src
    from socareguard.proxy.app import SpendMeter

    meter = SpendMeter(0)
    assert all(meter.has_room(1.0) and meter.charge(1.0) for _ in range(10))
    assert meter.report() is None


def test_the_panel_shows_the_budget_message_as_its_own_notice():
    js = (ROOT / "src/socareguard/proxy/static/panel.js").read_text()
    assert 'e.code === "daily_budget_exhausted"' in js
    assert "<strong>Shared daily limit reached.</strong>" in js
    assert "This applies to every visitor until the reset" in js
    assert 'e.code === "rate_limit_exceeded"' in js
