"""Proxy, compose and documentation behaviour changed after the 2026-09-28 review round 5: the
override's draft hash (SUP-F2), the per-session supervisor view (SUP-F1), retention in compose and
the start-up warning (DPO-F2), the vault key as a Docker secret (DPO-F3), the PDPC wording
(DPO-F4), the corpus v1.2 note (DPO-F5), the care-team note (DCM-F3) and the naming sentence."""

import hashlib
import logging
import re
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.proxy.core import Guard
from socareguard.scenarios.events import Flag, Screen

ROOT = Path(__file__).resolve().parent.parent
NOTE = "Client Tan Wei Ming, NRIC S1234567D, age 15, of Oakcrest Secondary School."
REPLY = "Dear principal, the young person was charged with theft last month."


def _text(rel: str) -> str:
    return " ".join((ROOT / rel).read_text().split())


class OneFlag:
    def screen(self, draft, pack, seq, instruction="", leaks=None, context="", **kw):
        f = Flag(label="I1", clause="A.7.c", severity="annotate", evidence=draft[:20])
        return [f], "annotate", [Screen(seq=seq, flags=[f])]


def _app(tmp_path, monkeypatch, retention=None):
    from socareguard.proxy import app as appmod

    g = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=OneFlag(),
    )
    monkeypatch.setattr(
        "socareguard.proxy.core.complete", lambda model, messages, **kw: (REPLY, {})
    )
    monkeypatch.setattr(appmod, "API_KEYS", set())
    if retention is not None:
        monkeypatch.setattr(appmod, "RETENTION_HOURS", retention)
    return TestClient(appmod.create_app(g))


def _send(client):
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Email the school.\n\n" + NOTE}]},
        headers={"X-SoCareGuard-Pack": "youth-offending"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _override(client, sg, **extra):
    body = {
        "session": sg["session"],
        "pack": "youth-offending",
        "flag_labels": ["I1"],
        "reason": "kept after discussion with the supervisor",
        **extra,
    }
    return client.post(
        "/v1/override", json=body, headers={"X-SoCareGuard-Session-Token": sg["session_token"]}
    )


# ---------- SUP-F2: an override on a session with a reply carries the draft hash ----------


def test_override_without_a_draft_hash_is_refused(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch)
    sg = _send(client)["socareguard"]
    for extra in ({}, {"draft_sha256": None}, {"draft_sha256": "abc"}, {"draft_sha256": "z" * 64}):
        r = _override(client, sg, **extra)
        assert r.status_code == 400
        assert "draft_sha256 is required" in r.json()["error"]["message"]
    rows = client.get(
        f"/v1/ledger?session={sg['session']}",
        headers={"X-SoCareGuard-Session-Token": sg["session_token"]},
    ).json()["rows"]
    assert all(r.get("decision") != "override" for r in rows)


def test_override_with_the_draft_hash_is_recorded(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch)
    body = _send(client)
    sg = body["socareguard"]
    h = hashlib.sha256(body["choices"][0]["message"]["content"].encode()).hexdigest()
    r = _override(client, sg, draft_sha256=h)
    assert r.status_code == 200
    assert r.json()["ledger_row"]["draft_sha256"] == h


def test_the_panel_sends_the_draft_hash():
    js = (ROOT / "src/socareguard/proxy/static/panel.js").read_text()
    assert re.search(r"JSON\.stringify\(\{[^}]*draft_sha256\}", js)


def test_readme_names_the_draft_hash_in_the_integration_text():
    readme = _text("README.md")
    assert "must also carry `draft_sha256`" in readme


# ---------- DPO-F2: retention in compose and the start-up warning ----------


def test_compose_sets_a_positive_retention():
    env = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]["socareguard"][
        "environment"
    ]
    assert env["SOCAREGUARD_RETENTION_HOURS"] == "720"


def test_startup_warns_when_retention_is_zero(tmp_path, monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="socareguard.proxy"):
        _app(tmp_path, monkeypatch, retention=0.0)
    recs = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("retention is disabled" in r.getMessage() for r in recs)


def test_startup_is_quiet_when_retention_is_set(tmp_path, monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="socareguard.proxy"):
        _app(tmp_path, monkeypatch, retention=720.0)
    assert not any("retention is disabled" in r.getMessage() for r in caplog.records)


def test_readme_states_the_retention_default_and_the_warning():
    readme = _text("README.md")
    assert "`SOCAREGUARD_RETENTION_HOURS=720`" in readme
    assert "logs a WARNING at start-up" in readme


# ---------- DPO-F3: the vault key from a Docker secret ----------


def test_compose_carries_the_secret_alternative_and_it_parses():
    src = (ROOT / "docker-compose.yml").read_text()
    assert "# SOCAREGUARD_VAULT_KEY: /run/secrets/socareguard_vault_key" in src
    uncommented = re.sub(r"(?m)^(\s*)# (SOCAREGUARD_VAULT_KEY|secrets:|  - socareguard|"
                         r"  socareguard_vault_key:|    file:)", r"\1\2", src)
    doc = yaml.safe_load(uncommented)
    svc = doc["services"]["socareguard"]
    assert svc["environment"]["SOCAREGUARD_VAULT_KEY"] == "/run/secrets/socareguard_vault_key"
    assert svc["secrets"] == ["socareguard_vault_key"]
    assert doc["secrets"]["socareguard_vault_key"]["file"] == "./secrets/socareguard_vault_key"


def test_vault_reads_the_key_from_a_secret_path(tmp_path, monkeypatch):
    import base64
    import os

    key_file = tmp_path / "secret"
    key_file.write_text(base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("SOCAREGUARD_VAULT_KEY", str(key_file))
    Vault(tmp_path / "vault" / "v.sqlite")
    assert not (tmp_path / "vault" / "v.key").exists()


def test_readme_states_the_key_default_and_the_option():
    readme = _text("README.md")
    assert "`vault/socareguard.key`, mode 600" in readme
    assert "mounts the key from a Docker secret" in readme
    assert "secrets/" in (ROOT / ".gitignore").read_text().split()


# ---------- DPO-F4, SUP-F1, naming ----------


def test_readme_pdpc_wording():
    readme = _text("README.md")
    assert "which PDPC's guidance treats as a data intermediary at inference" in readme
    assert "processes the pseudonymised payload as a data intermediary" not in readme


def test_readme_states_the_supervisor_view_is_per_session():
    readme = _text("README.md")
    assert "In the sandbox, the supervisor view is per session." in readme
    assert "`GET /v1/ledger` without a session lists the rows of all sessions" in readme


def test_readme_first_paragraph_names_title_and_artefact():
    first = _text("README.md").split("## ")[0]
    assert "professional-ethics guardrail" in first and "conduct taxonomy" in first


# ---------- DPO-F5, DCM-F3, scope list (b) ----------


def test_corpus_readmes_say_the_v12_drafts_are_unguarded():
    for rel in ("corpus/drafts/README-v1.2.md", "corpus/README.md"):
        t = _text(rel)
        assert "unguarded drafter output on synthetic notes" in t
        assert "NRICs" in t


def test_pack_readme_and_scope_name_the_care_team_tier():
    assert "including the client's own service providers" in _text("policy-packs/README.md")
    # The reserved list itself is private; the public pack README states the future-work note.
    assert "future work" in _text("policy-packs/README.md")
