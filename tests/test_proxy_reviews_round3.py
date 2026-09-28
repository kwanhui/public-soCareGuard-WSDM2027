"""Proxy, panel, snapshot and documentation behaviour changed after the 2026-09-28 review round 3:
the snapshot's .gitignore (IT-F1), sessions that survive a restart (IT-F2), 400 on a bad body
(IT-F3), logged pipeline failures (IT-F4), GLiNER2 in install-detect and the healthcheck (IT-F5,
IT-F6), the rewrite applied in place (COACH-F3), the UNRESTORED card and its count (COACH-F4,
UIUX-F2), the release line, the legend and the moderation caption (UIUX-F1, UIUX-F5, WSDM
legend), the override's request row (COMP-O1), and the documentation leftovers (COMP-N5, WSDM,
COACH-F5, UIUX-F3)."""

import importlib.util
import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.proxy.core import Guard
from socareguard.scenarios.events import Flag, Screen

ROOT = Path(__file__).resolve().parent.parent
NOTE = "Client Tan Wei Ming, NRIC S1234567D, age 15, of Oakcrest Secondary School. Mother Mdm Lim Siew Lan (9123 4567)."
REPLY = "Dear principal, the young person was charged with theft last month."
PANEL_JS = ROOT / "src/socareguard/proxy/static/panel.js"
REWRITE_JS = ROOT / "src/socareguard/proxy/static/rewrite.js"


class OneFlag:
    def __init__(self, label="I1", severity="annotate"):
        self.label, self.severity = label, severity

    def screen(self, draft, pack, seq, instruction="", leaks=None, context="", **kw):
        f = Flag(label=self.label, clause="A.7.c", severity=self.severity, evidence=draft[:20])
        return [f], self.severity, [Screen(seq=seq, flags=[f])]


def _app(tmp_path, monkeypatch, label="I1", severity="annotate"):
    """A fresh app on the vault and ledger under tmp_path, as a restarted server would open them."""
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
    return TestClient(appmod.create_app(g)), g


def _send(client, session=None):
    headers = {"X-SoCareGuard-Pack": "youth-offending"}
    if session:
        headers["X-SoCareGuard-Session"] = session
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Email the school.\n\n" + NOTE}]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["socareguard"]


def _override(client, sg, row=None, labels=("I1",)):
    body = {
        "session": sg["session"],
        "pack": "youth-offending",
        "flag_labels": list(labels),
        "reason": "kept after discussion with the supervisor",
        "draft_sha256": "ab" * 32,
    }
    if row is not None:
        body["request_row_sha256"] = row
    return client.post(
        "/v1/override", json=body, headers={"X-SoCareGuard-Session-Token": sg["session_token"]}
    )


# ---------- IT-F2: the session index survives a restart ----------


def test_a_session_survives_a_restart(tmp_path, monkeypatch):
    client, g = _app(tmp_path, monkeypatch)
    sg = _send(client)
    tok = {"X-SoCareGuard-Session-Token": sg["session_token"]}
    before = client.get(f"/v1/sessions/{sg['session']}", headers=tok).json()
    panel_before = client.get(f"/v1/sessions/{sg['session']}/panel", headers=tok).json()
    g.vault.close()

    client2, _ = _app(tmp_path, monkeypatch)  # a new process on the same vault directory
    r = client2.get(f"/v1/sessions/{sg['session']}", headers=tok)
    assert r.status_code == 200, r.text
    after = r.json()
    for k in ("decision", "withheld", "flags", "reply", "events"):
        assert after[k] == before[k], k
    assert client2.get(f"/v1/sessions/{sg['session']}/panel", headers=tok).json() == panel_before
    # the token still guards it
    wrong = {"X-SoCareGuard-Session-Token": "0" * 32}
    assert client2.get(f"/v1/sessions/{sg['session']}", headers=wrong).status_code == 403
    # an override after the restart still sees the raised flags
    assert _override(client2, sg).status_code == 200
    # a later request in the same session returns the same token
    assert _send(client2, sg["session"])["session_token"] == sg["session_token"]


def test_a_withheld_draft_can_be_released_after_a_restart(tmp_path, monkeypatch):
    client, g = _app(tmp_path, monkeypatch, "I14", "escalate")
    sg = _send(client)
    assert sg["withheld"]
    url = f"/v1/sessions/{sg['session']}/withheld?reason=safeguarding%20review"
    h = {
        "X-SoCareGuard-Role": "supervisor",
        "X-SoCareGuard-Session-Token": sg["session_token"],
        "X-SoCareGuard-Actor": "sup-9007",
    }
    first = client.get(url, headers=h).json()
    g.vault.close()

    client2, _ = _app(tmp_path, monkeypatch, "I14", "escalate")
    r = client2.get(url, headers={**h, "X-SoCareGuard-Actor": "sup-another"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "charged with theft" in body["reply"]
    assert [p["row_sha256"] for p in body["prior_releases"]] == [first["ledger_row"]["row_sha256"]]


def test_the_index_keeps_the_reply_and_the_token_encrypted(tmp_path, monkeypatch):
    import sqlite3

    client, g = _app(tmp_path, monkeypatch)
    sg = _send(client)
    g.vault.close()
    raw = (tmp_path / "v.sqlite").read_bytes()
    assert b"charged with theft" not in raw and b"Tan Wei Ming" not in raw
    assert sg["session_token"].encode() not in raw
    row = (
        sqlite3.connect(tmp_path / "v.sqlite")
        .execute(
            "SELECT pack, withheld, flags FROM session_index WHERE session=?", (sg["session"],)
        )
        .fetchone()
    )
    assert row == ("youth-offending", 0, '["I1"]')


def test_a_purged_session_is_gone_after_a_restart(tmp_path, monkeypatch):
    client, g = _app(tmp_path, monkeypatch)
    sg = _send(client)
    tok = {"X-SoCareGuard-Session-Token": sg["session_token"]}
    assert client.delete(f"/v1/sessions/{sg['session']}", headers=tok).status_code == 200
    g.vault.close()
    client2, _ = _app(tmp_path, monkeypatch)
    assert client2.get(f"/v1/sessions/{sg['session']}", headers=tok).status_code == 404


# ---------- IT-F3, IT-F4: 400 on a bad body, a logged 503 with an error id ----------


def test_malformed_json_returns_400_in_the_openai_envelope(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    r = client.post(
        "/v1/chat/completions",
        content=b'{"messages": [{"role": "user", "cont',
        headers={"Content-Type": "application/json", "X-SoCareGuard-Pack": "disability"},
    )
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["type"] == "invalid_request_error" and err["code"] == "invalid_json"
    missing = client.post(
        "/v1/chat/completions", json={"model": "x"}, headers={"X-SoCareGuard-Pack": "disability"}
    )
    assert missing.status_code == 400 and missing.json()["error"]["code"] == "invalid_body"


def test_a_pipeline_failure_is_logged_with_the_id_the_503_carries(tmp_path, monkeypatch, caplog):
    client, _ = _app(tmp_path, monkeypatch)

    def boom(model, messages, **kw):
        raise ValueError("provider exploded")

    monkeypatch.setattr("socareguard.proxy.core.complete", boom)
    with caplog.at_level(logging.ERROR, logger="socareguard.proxy"):
        r = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Email the school.\n\n" + NOTE}]},
            headers={"X-SoCareGuard-Pack": "youth-offending"},
        )
    assert r.status_code == 503
    m = re.search(r"error ([0-9a-f]{8}) in the server log", r.json()["error"]["message"])
    assert m, r.json()
    recs = [
        x for x in caplog.records if x.levelno == logging.ERROR and m.group(1) in x.getMessage()
    ]
    assert recs and recs[0].exc_info and "provider exploded" in str(recs[0].exc_info[1])
    assert "S1234567D" not in recs[0].getMessage()


# ---------- COMP-O1: the override names a ledger row of its session ----------


def test_override_refuses_a_request_row_that_is_not_in_the_session(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    sg = _send(client)
    other = _send(client)
    r = _override(client, sg, "0" * 64)
    assert r.status_code == 400 and "ledger row of this session" in r.json()["error"]["message"]
    # a real row, but of another session
    assert _override(client, sg, other["ledger_row_sha256"]).status_code == 400
    ok = _override(client, sg, sg["ledger_row_sha256"])
    assert ok.status_code == 200
    assert ok.json()["ledger_row"]["request_row_sha256"] == sg["ledger_row_sha256"]


def test_override_without_a_request_row_points_at_the_latest_request(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    sg = _send(client)
    r = _override(client, sg)
    assert r.status_code == 200
    assert r.json()["ledger_row"]["request_row_sha256"] == sg["ledger_row_sha256"]


# ---------- IT-F1: the snapshot's .gitignore ----------


def _snapshot_gitignore() -> str:
    sh = (ROOT / "scripts/make_public_snapshot.sh").read_text()
    m = re.search(r"<<'GITIGNORE'\n(.*?)\nGITIGNORE\n", sh, re.DOTALL)
    assert m, "the snapshot script does not write a .gitignore heredoc"
    return m.group(1)


@pytest.mark.skipif(not (ROOT / "scripts").exists(), reason="not shipped in the public snapshot")
def test_snapshot_gitignore_covers_runtime_state_and_keys(tmp_path):
    body = _snapshot_gitignore()
    for line in (
        "__pycache__/",
        "*.pyc",
        "vault/",
        "*.key",
        ".env",
        ".local/",
        "*.sqlite",
        "*.sqlite3",
    ):
        assert line in body.splitlines(), line
    git = shutil.which("git")
    if not git:
        pytest.skip("git is not installed")
    subprocess.run([git, "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(body + "\n")
    paths = ["vault/x.key", ".env", "vault/ledger.jsonl", "vault/socareguard.sqlite", "other.key"]
    out = subprocess.run(
        [git, "-C", str(tmp_path), "check-ignore", *paths],
        capture_output=True,
        text=True,
        check=False,
    )
    assert sorted(out.stdout.split()) == sorted(paths)
    kept = subprocess.run(
        [git, "-C", str(tmp_path), "check-ignore", ".env.example", "src/a.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert kept.returncode == 1 and not kept.stdout


# ---------- IT-F5, IT-F6 ----------


def test_install_detect_installs_gliner2_and_the_images_have_a_healthcheck():
    make = (ROOT / "Makefile").read_text()
    target = make[make.index("install-detect:") :].split("\n\n")[0]
    assert "gliner2" in target
    assert re.search(
        r"^HEALTHCHECK .*\n?.*healthz", (ROOT / "Dockerfile").read_text(), re.MULTILINE
    )
    import yaml

    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    hc = compose["services"]["socareguard"]["healthcheck"]
    assert any("/healthz" in part for part in hc["test"])


# ---------- COACH-F3: the rewrite applied in place ----------


def _node(expr: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    code = f"const r = require({json.dumps(str(REWRITE_JS))}); console.log(JSON.stringify({expr}));"
    out = subprocess.run([node, "-e", code], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


COACH = (
    "I am writing to introduce Priya, who will be coming for a trial shift at your cafe. Priya is 29 "
    "years old and has a moderate developmental disability. She communicates best using a "
    "communication board alongside speech.\n\nFor her trial shift, Priya will be accompanied by a job "
    "coach to support her during the session."
)


def test_a_rewrite_replaces_the_flagged_text_without_repeating_the_letter():
    ev = "Priya is 29 years old and has a moderate developmental disability."
    rw = (
        "Priya communicates best using a communication board alongside speech. She will be "
        "accompanied by a job coach during her trial shift."
    )
    out = _node(f"r.applyRewrite({json.dumps(COACH)}, {json.dumps(ev)}, {json.dumps(rw)})")
    assert out["status"] == "replaced"
    assert ev not in out["text"]
    assert out["text"].count("communication board") == 1 and out["text"].count("job coach") == 1
    assert len(out["dropped"]) == 2


def test_a_new_rewrite_sentence_lands_where_the_flagged_text_was():
    ev = "Priya is 29 years old and has a moderate developmental disability."
    rw = "Priya will start with short tasks at the counter."
    out = _node(f"r.applyRewrite({json.dumps(COACH)}, {json.dumps(ev)}, {json.dumps(rw)})")
    assert out["status"] == "replaced" and out["dropped"] == []
    assert (
        "your cafe. Priya will start with short tasks at the counter. She communicates"
        in out["text"]
    )


def test_a_sentence_rewrite_of_a_phrase_replaces_its_sentence():
    out = _node(
        f"r.applyRewrite({json.dumps(COACH)}, 'moderate developmental disability', "
        "'Priya has a developmental disability.')"
    )
    assert "has a Priya" not in out["text"]
    assert "your cafe. Priya has a developmental disability. She communicates" in out["text"]


def test_a_rewrite_whose_text_is_not_found_changes_nothing():
    out = _node(
        f"r.applyRewrite({json.dumps(COACH)}, 'This sentence is not in the letter at all.', "
        "'A new sentence.')"
    )
    assert out["status"] == "not_found" and out["text"] == COACH


def test_the_panel_shows_an_unfound_rewrite_for_manual_use():
    js = PANEL_JS.read_text()
    fn = js[js.index("async function acceptRewrite") : js.index('$("release-form")')]
    assert 'out.status === "not_found"' in fn and "manual-${i}" in fn
    assert "Place this rewrite yourself" in fn
    not_found = fn[fn.index('out.status === "not_found"') : fn.index("return;")]
    assert "message.content" not in not_found and "ledgerWrite" not in not_found
    assert (
        '<script src="/static/rewrite.js"></script>'
        in (ROOT / "src/socareguard/proxy/templates/panel.html").read_text()
    )


# ---------- COACH-F4, UIUX-F2, UIUX-F1, UIUX-F5, WSDM legend ----------


def test_the_unrestored_card_is_major_and_the_legend_counts_its_list():
    js = PANEL_JS.read_text()
    assert "const unrestored = unrestoredWords(leak);" in js
    assert "[].concat(leak.unrestored || [], leak.partial || [])" in js
    assert "stand-in not restored: ${unrestored.length}" in js
    assert 'isUnrestored ? " major" : ""' in js and "major: replace before use" in js
    assert '<div class="unrestored-list">' in js
    assert "leak.unrestored.length" not in js and "leak.n_unrestored" not in js
    css = (ROOT / "src/socareguard/proxy/static/panel.css").read_text()
    assert ".flag.major" in css and ".pill.major" in css


def test_the_legend_release_line_and_moderation_caption():
    js = PANEL_JS.read_text()
    assert (
        "Clause codes refer to the SASW Code or to the statute named on the card. DV-n and "
        "similar codes are pack rules."
    ) in js
    assert "); identity" not in js
    # round 6 acceptance: one pair of parentheses around the actor ("admin (sandbox login, typed
    # in)"), then the time
    assert (
        'Released earlier by ${actorLabel(x.actor, x.actor_attested)}, ${x.ts ? utc(x.ts) : "time not recorded"}.'
        in js
    )
    assert 'BASELINE_CAPTION = "generic harm classifier, shown for contrast"' in js
    assert '<span class="segcap">(${BASELINE_CAPTION})</span>' in js


# ---------- documentation ----------


def test_readme_names_the_three_pdpc_roles_once_and_the_new_limits():
    readme = (ROOT / "README.md").read_text()
    flat = " ".join(readme.split())
    for role in ("System Deployer", "System Provider", "Model Provider"):
        assert role in flat, role
    assert flat.count("Model Provider") == 1
    assert "as a data intermediary" in flat
    assert "a path to a key file or the key itself" in flat
    assert (
        "Language that the practitioner wrote in the note may be echoed by the model without a flag"
        in flat
    )
    assert "in preparation" not in readme.split("## Roadmap")[1].split("##")[0]
    assert "under review after that date" in flat
    assert "Open sessions survive a restart" in flat


def test_leftovers_are_gone():
    assert "screen-v1`" not in (ROOT / "demo/README.md").read_text()
    assert "estimate_cost" not in (ROOT / "docs/metrics.md").read_text()
    assert "estimate_cost" not in (ROOT / "src/socareguard/eval/report.py").read_text()
    assert "- **Real**" not in (ROOT / "corpus/README.md").read_text()
    for rel in ("README.md", "demo/README.md", "policy-packs/README.md"):
        text = " ".join((ROOT / rel).read_text().split())
        # "Ethics" appears only in the quoted title of the SASW Code, and in README once in the
        # round-5 naming sentence that says the paper's title names the domain
        naming = "The paper's title names the domain (a professional-ethics guardrail)"
        if rel == "README.md":
            assert text.count(naming) == 1
            text = text.replace(naming, "")
        for m in re.finditer(r"[Ee]thics", text):
            assert text[max(0, m.start() - 40) : m.end()].endswith("Code of Professional Ethics"), (
                rel
            )


@pytest.mark.skipif(not (ROOT / "scripts").exists(), reason="not shipped in the public snapshot")
def test_touched_files_carry_no_semicolon_splice():
    spec = importlib.util.spec_from_file_location("check_prose", ROOT / "scripts/check_prose.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    rules = cp.load_allow()
    for rel in (
        "README.md",
        "demo/README.md",
        "policy-packs/README.md",
        "corpus/README.md",
        "src/socareguard/proxy/static/panel.js",
        "src/socareguard/proxy/static/rewrite.js",
    ):
        warnings = [line for line in cp.scan(ROOT / rel, rules) if "semicolon-splice" in line]
        assert not warnings, warnings
