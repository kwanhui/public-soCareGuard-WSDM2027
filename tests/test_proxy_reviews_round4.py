"""Proxy, panel and documentation behaviour changed after the 2026-09-28 review round 4: the
echoed-wording clause on the legend (STU-N1), the pack-default header for API callers (FSC-F5),
the mark on a restored never-leak span (UIUX-F2), the two-sentence audience hint (UIUX-F3), and
the README's reproducibility, format and corpus sentences (WSDM-N1, WSDM-N2, WSDM-N7)."""

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.proxy.core import Guard

ROOT = Path(__file__).resolve().parent.parent
PANEL_JS = ROOT / "src/socareguard/proxy/static/panel.js"
PANEL_HTML = ROOT / "src/socareguard/proxy/templates/panel.html"
PANEL_CSS = ROOT / "src/socareguard/proxy/static/panel.css"
NOTE = "Client Tan Wei Ming, NRIC S1234567D, age 15. Mother Mdm Lim Siew Lan (9123 4567)."
ECHO = "Wording that the note itself uses may be echoed without a flag."


def _client(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    monkeypatch.setenv("SOCAREGUARD_SCREEN", "off")
    g = Guard(vault=Vault(tmp_path / "v.sqlite"), ledger=Ledger(tmp_path / "l.jsonl"),
              use_presidio=False, use_gliner=False)
    monkeypatch.setattr("socareguard.proxy.core.complete",
                        lambda model, messages, **kw: ("Summary for the case file.", {}))
    monkeypatch.setattr(appmod, "API_KEYS", set())
    return TestClient(appmod.create_app(g))


def _post(client, headers):
    return client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Summarise this note.\n\n" + NOTE}]},
        headers=headers,
    )


# ---------- FSC-F5: the pack default is visible in a header ----------

def test_a_defaulted_pack_sets_the_header(tmp_path, monkeypatch):
    r = _post(_client(tmp_path, monkeypatch), {})
    assert r.status_code == 200, r.text
    assert r.json()["socareguard"]["pack_defaulted"] is True
    assert r.headers.get("X-SoCareGuard-Pack-Defaulted") == "true"


def test_a_named_pack_sets_no_header(tmp_path, monkeypatch):
    r = _post(_client(tmp_path, monkeypatch), {"X-SoCareGuard-Pack": "youth-offending"})
    assert r.status_code == 200, r.text
    assert r.json()["socareguard"]["pack_defaulted"] is False
    assert "X-SoCareGuard-Pack-Defaulted" not in r.headers


def test_the_readme_and_the_panel_name_the_header():
    flat = " ".join((ROOT / "README.md").read_text().split())
    assert "`X-SoCareGuard-Pack-Defaulted: true`" in flat
    assert "<code>X-SoCareGuard-Pack-Defaulted: true</code>" in PANEL_HTML.read_text()


# ---------- STU-N1: the legend says that echoed wording may pass unflagged ----------

def test_the_flag_legend_and_the_closing_line_carry_the_echo_clause():
    assert ECHO in PANEL_JS.read_text()
    assert ECHO in PANEL_HTML.read_text()


# ---------- UIUX-F2: a restored never-leak span is marked in column 4 ----------

def test_a_restored_generalised_span_is_marked():
    js = PANEL_JS.read_text()
    assert 'label: `${cls(r)} restored`' in js
    assert '"withheld outbound, restored here"' in js
    # the panel's replacement table names a never-leak span by its rule, "<pack>.never_leak"
    assert '/\\.never_leak$/.test(r.rule || "")' in js
    assert 'id="legend-restored"' in js
    assert "mark.restored {" in PANEL_CSS.read_text()
    assert "restored from the record and underlined in dots" in PANEL_HTML.read_text()


# ---------- UIUX-F3: the audience hint is two sentences, the employer rule sits in column 2 ----------

def test_the_audience_hint_is_two_sentences_and_the_employer_rule_moved():
    html = PANEL_HTML.read_text()
    hint = html.split('id="audience-hint">')[1].split("</span>")[0]
    # round 6: the field is "Recipient", one short hint (docs/terminology.md) that names no flag
    # code; the codes and the care-team clause sit in the field's own "More"
    assert hint == "Who the draft is for. Some flags depend on it."
    more = html.split('id="audience-more">')[1].split("</details>")[0]
    assert "I10" in more and "I14" in more
    assert "For the client's care team, I10 is read within the recipient's role (a draft reading)." in more
    col2 = html.split("<h2>What left the premises</h2>")[1].split("</article>")[0]
    assert ('A named employer leaves as an invented name for a recipient inside the agency and '
            'as "an employer" for one outside it.') in col2


# ---------- WSDM-N1, N2, N7: README ----------

def test_readme_states_the_measurement_tag_formats_and_compliant_drafts():
    flat = " ".join((ROOT / "README.md").read_text().split())
    assert "measured at tag `results-v1.3`" in flat
    assert "`results-v1.1` values are kept" in flat
    assert "canonical formats of the corpus generator" in flat
    assert "format-variant stress set" in flat
    assert "The compliant drafts of corpus v1.1 are all internal summaries" in flat
    assert "Corpus v1.2 adds 90 compliant external drafts" in flat


@pytest.mark.skipif(not (ROOT / "scripts").exists(), reason="not shipped in the public snapshot")
def test_touched_files_pass_the_prose_checker():
    spec = importlib.util.spec_from_file_location("check_prose", ROOT / "scripts/check_prose.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    rules = cp.load_allow()
    for rel in ("README.md", "src/socareguard/proxy/static/panel.js",
                "src/socareguard/proxy/templates/panel.html"):
        assert not list(cp.scan(ROOT / rel, rules)), rel
