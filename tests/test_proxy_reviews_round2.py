"""Proxy, panel, snapshot and prose-tooling behaviour changed after the 2026-09-28 review round 2:
the release button (UIUX-N1), the flag legend and confidence label (STU-F2), the rewrite caption
(STU-F4), the pack provenance (FSC-F5, STU-F5), reason truncation and the underline fallback
(ETH-F4, STU-F6), the drafts in the snapshot (WSDM-N3), the semicolon-splice warning (UIUX-N3)
and the per-person surrogate limitation (FSC-F3)."""

import importlib.util
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.proxy.app import REASON_CAP, display_reason
from socareguard.proxy.core import Guard
from socareguard.scenarios.events import Flag, Screen

ROOT = Path(__file__).resolve().parent.parent
NOTE = "Client Tan Wei Ming, NRIC S1234567D, age 15, of Oakcrest Secondary School. Mother Mdm Lim Siew Lan (9123 4567)."
REPLY = "Dear principal, the young person was charged with theft last month."
LONG_REASON = (
    "The draft describes the survivor's decision to return home as a choice made against advice, "
    "which could be interpreted as attributing responsibility to the client for risk, contrary to "
    "the clause that asks the worker to describe the client's circumstances without judgement and "
    "to record the risk factors that remain with the person who caused the harm in the household"
)[:REASON_CAP]  # a plain slice, as the judge applies it, ends mid-word


class LongReason:
    def screen(self, draft, pack, seq, instruction="", leaks=None, context="", **kw):
        f = Flag(
            label="I1",
            clause="A.7.c",
            severity="annotate",
            evidence=draft[:20],
            rewrite="Dear principal, the young person is known to the service.",
            reason=LONG_REASON,
            confidence=0.95,
        )
        return [f], "annotate", [Screen(seq=seq, flags=[f])]


def _client(tmp_path, monkeypatch, sandbox=False):
    from socareguard.proxy import app as appmod

    g = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=LongReason(),
    )
    monkeypatch.setattr(
        "socareguard.proxy.core.complete", lambda model, messages, **kw: (REPLY, {})
    )
    monkeypatch.setattr(appmod, "API_KEYS", set())
    monkeypatch.setattr(appmod, "SANDBOX", sandbox)
    return TestClient(appmod.create_app(g))


def _send(client, pack="youth-offending"):
    headers = {"X-SoCareGuard-Pack": pack} if pack else {}
    return client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Email the school.\n\n" + NOTE}]},
        headers=headers,
    ).json()["socareguard"]


# ---------- ETH-F4: reason truncation ----------


def test_a_cut_reason_ends_on_a_whole_word_with_an_ellipsis():
    assert not LONG_REASON.endswith(" ") and LONG_REASON[-1].isalpha()
    out = display_reason(LONG_REASON)
    assert out.endswith("…")
    body = out[:-1]
    assert LONG_REASON.startswith(body)
    assert LONG_REASON[len(body)] == " "  # the cut falls on a space, not inside a word
    assert len(out) <= REASON_CAP


@pytest.mark.parametrize(
    "reason",
    [
        "",
        "Blaming language about the survivor's ambivalence (I1).",
        "A short reason without a full stop",
        ("x " * 140) + "and it ends here.",
    ],
)
def test_a_reason_that_was_not_cut_is_unchanged(reason):
    assert display_reason(reason) == reason.rstrip()


def test_a_word_bounded_reason_near_the_cap_gains_only_the_ellipsis():
    # what the judge returns once it truncates at a word boundary itself
    head = LONG_REASON[: LONG_REASON.rfind(" ")]
    assert display_reason(head) == head.rstrip(" ,") + "…"


def test_the_completion_and_the_release_carry_the_tidied_reason(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    sg = _send(client)
    reason = sg["flags"][0]["reason"]
    assert reason.endswith("…") and reason == display_reason(LONG_REASON)
    tok = {"X-SoCareGuard-Session-Token": sg["session_token"]}
    assert (
        client.get(f"/v1/sessions/{sg['session']}", headers=tok).json()["flags"][0]["reason"]
        == reason
    )


# ---------- FSC-F5, STU-F5: the pack is never silent ----------


def test_a_request_without_a_pack_says_the_default_ran(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    client = _client(tmp_path, monkeypatch)
    sg = _send(client, pack=None)
    assert sg["pack_defaulted"] is True and sg["pack"] == appmod.DEFAULT_PACK
    assert _send(client)["pack_defaulted"] is False


def test_the_panel_shows_the_pack_and_where_it_came_from(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    page = _client(tmp_path, monkeypatch, sandbox=True).get("/").text
    assert 'id="pack-hint"' in page and 'aria-describedby="pack-hint"' in page
    assert f'<option value="{appmod.DEFAULT_PACK}" selected>' in page
    js = (ROOT / "src/socareguard/proxy/static/panel.js").read_text()
    assert 'pack: ${esc(sg.pack)}${sg.pack_defaulted ? " (default)" : ""}' in js
    assert "Set by the scenario: ${s.pack}." in js
    assert 'Kept from the scenario: ${$("pack").value}. Check that it fits your note.' in js
    assert 'Chosen by you: ${$("pack").value}.' in js


# ---------- STU-F2, STU-F4, UIUX-N1, STU-F6: panel wording and behaviour ----------


def test_panel_script_carries_the_round_two_wording():
    js = (ROOT / "src/socareguard/proxy/static/panel.js").read_text()
    # round 3 (WSDM legend) widened the first sentence of the legend; the rest is unchanged
    assert (
        "Precision is measured on synthetic drafts (v1.2). Confidence is the judge's own estimate."
    ) in js
    assert "judge's own confidence ${f.confidence.toFixed(2)}" in js
    assert "judge confidence ${" not in js
    assert ">Use this rewrite (your decision, recorded)</button>" in js
    assert 'ledgerWrite("rewrite_accepted"' in js
    assert "the flag card below quotes the full text" in js


def test_release_button_re_enables_after_success():
    js = (ROOT / "src/socareguard/proxy/static/panel.js").read_text()
    handler = js[
        js.index('$("release-form").addEventListener') : js.index(
            '$("regenerate").addEventListener'
        )
    ]
    assert re.search(r"finally\s*\{\s*btn\.disabled = false;", handler)


def test_rewrite_accepted_is_written_to_the_ledger(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    sg = _send(client)
    r = client.post(
        "/v1/override",
        headers={"X-SoCareGuard-Session-Token": sg["session_token"]},
        json={
            "session": sg["session"],
            "pack": "youth-offending",
            "flag_labels": ["I1"],
            "reason": "suggested rewrite applied in the panel",
            "kind": "rewrite_accepted",
            "request_row_sha256": sg["ledger_row_sha256"],
            "draft_sha256": "ab" * 32,
        },
    )
    assert r.status_code == 200
    assert r.json()["ledger_row"]["decision"] == "rewrite_accepted"


def test_underline_falls_back_to_the_first_sentence(tmp_path):
    """Runs the panel's own matching functions under node when it is installed."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    js = (ROOT / "src/socareguard/proxy/static/panel.js").read_text()
    start = js.index("  const isWord")
    end = js.index("  function md(h)")
    harness = (
        "const esc = (s) => String(s);\n"
        + f"const window = {{SoCareGuardRewrite: require({json.dumps(str(ROOT / 'src/socareguard/proxy/static/rewrite.js'))})}};\n"
        + js[start:end]
        + "function md(h) { return h; }\n"
        + "function highlight(text, spans) { return spans.map((s) => text.slice(s.start, s.end)); }\n"
        + "const draft = 'Here are the recommended next steps to support\\n**Mdm Farah** and her family:\\n1. Visit.';\n"
        + "const ev = 'Here are the recommended next steps to support Mdm Farah and her family: ... 1. ...';\n"
        + "console.log(JSON.stringify(markAll(draft, [{text: ev, label: 'evidence', fuzzy: true}])));\n"
        + "console.log(JSON.stringify(markAll(draft, [{text: 'Nothing like this is in the draft at all.', label: 'evidence', fuzzy: true}])));\n"
    )
    f = tmp_path / "h.js"
    f.write_text(harness)
    out = subprocess.run([node, str(f)], capture_output=True, text=True, check=True).stdout.split(
        "\n"
    )
    assert out[0].startswith(
        '["Here are the recommended next steps to support\\n**Mdm Farah** and her family"'
    )
    assert out[1] == "[]"


# ---------- UIUX-N3: splices rewritten, and the checker's warning ----------


@pytest.mark.skipif(not (ROOT / "scripts").exists(), reason="not shipped in the public snapshot")
def test_panel_and_readmes_carry_no_semicolon_splice():
    spec = importlib.util.spec_from_file_location("check_prose", ROOT / "scripts/check_prose.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    rules = cp.load_allow()
    for rel in (
        "README.md",
        "demo/README.md",
        "policy-packs/README.md",
        "src/socareguard/proxy/templates/panel.html",
        "src/socareguard/proxy/static/panel.js",
    ):
        warnings = [line for line in cp.scan(ROOT / rel, rules) if "semicolon-splice" in line]
        assert not warnings, warnings


@pytest.mark.skipif(not (ROOT / "scripts").exists(), reason="not shipped in the public snapshot")
def test_check_prose_warns_on_a_splice_and_not_on_a_list(tmp_path):
    spec = importlib.util.spec_from_file_location("check_prose", ROOT / "scripts/check_prose.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    md = tmp_path / "x.md"
    md.write_text(
        "The chain is tamper-evident against edits and\nreordering; anchoring the head hash is the deployer's step.\n\n"
        "- A bullet that joins two clauses is left alone; the list reads as notes.\n\n"
        "> A quoted note says she stayed at the shelter; she is worried about the school.\n\n"
        "Short one; short two.\n\n"
        "The packs cover three settings: (a) disability services; (b) family violence work.\n"
    )
    warnings = [line for line in cp.scan(md, []) if "semicolon-splice" in line]
    assert len(warnings) == 1 and ":2: semicolon-splice:" in warnings[0]
    assert warnings[0].startswith("warning: ")
    assert cp.main([str(md), "--allow", str(tmp_path / "none.txt")]) == 0
    assert cp.main([str(md), "--allow", str(tmp_path / "none.txt"), "--strict"]) == 1


# ---------- WSDM-N3: drafts in the snapshot, not in the image ----------


@pytest.mark.skipif(not (ROOT / "scripts").exists(), reason="not shipped in the public snapshot")
def test_snapshot_allowlist_carries_the_drafts_and_the_image_does_not():
    sh = (ROOT / "scripts/make_public_snapshot.sh").read_text()
    allow = sh[sh.index("allowlist=(") : sh.index(")", sh.index("allowlist=("))]
    assert "corpus/drafts" in allow.split()
    assert "scripts" not in allow.split()
    assert "corpus/drafts" in (ROOT / ".dockerignore").read_text().split()
    readme = (ROOT / "README.md").read_text()
    assert "the synthetic notes and drafts with their labels" in " ".join(readme.split())


# ---------- FSC-F3: per-person surrogates are stated ----------


def test_per_person_surrogates_are_stated(tmp_path, monkeypatch):
    readme = " ".join((ROOT / "README.md").read_text().split())
    assert (
        "Surrogates are per person. Two people who share a surname receive unrelated surrogate "
        'surnames, so a sentence such as "same surname as the client" does not survive '
        "substitution."
    ) in readme
    page = _client(tmp_path, monkeypatch, sandbox=True).get("/").text
    assert "Surrogates are per person" in page
