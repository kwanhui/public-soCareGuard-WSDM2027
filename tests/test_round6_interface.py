"""Round 6, work package D: the interface pass.

The result banner (one status sentence, one next step, one filled button per decision), the
columns (what left the premises open, the reply with stand-ins collapsed), the flag cards with a
plain-words headline for every category, the release confirmation, and the accessibility run.

The browser tests drive the panel over a local server whose screen is keyed on the instruction,
so each of the four decisions is rendered by the page's own script. They are skipped when
Playwright or its Chromium is not installed. The axe run needs a local copy of axe-core named by
SOCAREGUARD_AXE_JS (the file is not vendored in this repository). Its JSON is written to
SOCAREGUARD_AXE_OUT when that is set, else to the test's temporary directory.
"""

from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
from html.parser import HTMLParser
from pathlib import Path

import pytest

from socareguard.ledger import Ledger
from socareguard.outbound.vault import Vault
from socareguard.proxy.core import Guard
from socareguard.scenarios.events import Flag, Screen
from socareguard.taxonomy import INBOUND

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "src/socareguard/proxy/templates"
STATIC = ROOT / "src/socareguard/proxy/static"
PANEL_HTML = TEMPLATES / "panel.html"
PANEL_JS = STATIC / "panel.js"

# decision -> (next step, button label)
BANNER = {
    "pass": ("Nothing to flag. Copy the draft.", "Copy the draft"),
    "annotate": (
        "Read each flag, then use the rewrite or keep the passage with a reason.",
        "Go to the first flag",
    ),
    "regenerate": ("Regenerate with the flags as instructions.", "Regenerate"),
    "escalate": ("Give the session id to your supervisor.", "Copy the session id"),
}


class _Tree(HTMLParser):
    """Each element as (tag, attrs, ancestors), enough to ask where an id sits."""

    VOID = frozenset({"meta", "link", "input", "br", "img", "hr", "source", "area", "col", "wbr"})

    def __init__(self, html: str):
        super().__init__()
        self.stack: list = []
        self.elements: list = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        el = (tag, dict(attrs), list(self.stack))
        self.elements.append(el)
        if tag not in self.VOID:
            self.stack.append(el)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def by_id(self, id_):
        return next(e for e in self.elements if e[1].get("id") == id_)


# ---------- static checks ----------


def test_the_banner_has_one_filled_button_and_the_four_texts():
    html, js = PANEL_HTML.read_text(), PANEL_JS.read_text()
    tree = _Tree(html)
    primary = [e for e in tree.elements if "btn-primary" in (e[1].get("class") or "").split()]
    in_result = [e for e in primary if any(a[1].get("id") == "result" for a in e[2])]
    assert [e[1].get("id") for e in in_result] == ["decision-action"]
    assert [e[1].get("id") for e in primary if e not in in_result] == ["send"]
    # no script adds another filled button
    assert "btn-primary" not in js
    for decision, (nxt, label) in BANNER.items():
        assert f'{decision}: {{next: "{nxt}", action: "{label}"}}' in js
    for id_ in ("decision-title", "decision-next", "decision-action", "decision-more"):
        assert any(a[1].get("id") == "decision" for a in tree.by_id(id_)[2]), id_
    # the glossary line sits inside "More"
    assert any(a[1].get("id") == "decision-more" for a in tree.by_id("glossary")[2])


def test_what_left_is_open_and_the_reply_with_stand_ins_is_collapsed():
    tree = _Tree(PANEL_HTML.read_text())
    details = tree.by_id("col-back-details")
    assert details[0] == "details" and "open" not in details[1]
    assert any(a[1].get("id") == "col-back-details" for a in tree.by_id("col-back")[2])
    for col in ("col-typed", "col-out", "col-seen"):
        assert not any(a[0] == "details" for a in tree.by_id(col)[2]), col
    heads = re.findall(r"<h2>([^<]+)</h2>", PANEL_HTML.read_text())
    for h in (
        "What you typed",
        "What left the premises",
        "What the model replied (with stand-ins)",
        "What you see",
    ):
        assert h in heads, h


def test_the_release_waits_for_the_confirmation():
    tree = _Tree(PANEL_HTML.read_text())
    confirm = tree.by_id("release-confirm")
    assert "hidden" in confirm[1]
    assert any(a[1].get("id") == "release-form" for a in confirm[2])
    js = PANEL_JS.read_text()
    handler = js[
        js.index('$("release-form").addEventListener') : js.index(
            "  // ---------- read-only review"
        )
    ]
    assert handler.index("if (!releaseConfirmed)") < handler.index("await fetch(")
    assert re.search(r"finally\s*\{\s*btn\.disabled = false; releaseConfirmed = false;", handler)
    yes = js[js.index('$("release-confirm-yes")') :].split("\n")[0]
    assert "releaseConfirmed = true" in yes and "requestSubmit()" in yes


def test_escalation_note_is_an_alert_with_the_session_row():
    tree = _Tree(PANEL_HTML.read_text())
    assert tree.by_id("escalate-note")[1].get("role") == "alert"
    js = PANEL_JS.read_text()
    assert '<div class="sessionid" id="escalate-session">' in js and 'id="copy-session"' in js


def test_every_category_has_a_plain_headline(tmp_path, monkeypatch):
    assert len(INBOUND) == 15
    for c in INBOUND:
        assert c.plain and len(c.plain) <= 90, c.id
        assert c.plain[0].isupper() and not c.plain.endswith("."), c.id
        assert not re.search(r"\b(?:[A-D]\.\d|I\d+|SASW|CYPA|judge|audience)\b", c.plain), c.id
    assert len({c.plain for c in INBOUND}) == 15
    i10 = next(c for c in INBOUND if c.id == "I10")
    assert i10.plain == "Tells the recipient something the client did not agree to share"
    page = _client(tmp_path, monkeypatch).get("/").text
    taxonomy = json.loads(page.split("window.TAXONOMY = ")[1].split("; window.PRECISION")[0])
    assert {k: v["plain"] for k, v in taxonomy.items()} == {c.id: c.plain for c in INBOUND}


def test_flag_cards_lead_with_the_plain_words_and_keep_both_numbers():
    js = PANEL_JS.read_text()
    card = js[js.index("// flag cards:") : js.index('const note = $("escalate-note")')]
    assert "<h3>${esc(plainOf(f))}</h3>" in card
    meta = card[
        card.index('<p class="flag-meta">') : card.index(
            "</p>", card.index('<p class="flag-meta">')
        )
    ]
    assert "the screen's own confidence" in card and "precisionText(f.label)" in card
    assert "${nums}" in meta or "esc(nums)" in meta
    assert 'class="btn-card accept"' in card and ">Use this rewrite</button>" in card
    assert '${f.rewrite ? "btn-quiet" : "btn-card"}">Keep with a reason</summary>' in card


# ---------- the browser ----------


def _playwright_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            p.chromium.launch().close()
    except Exception:  # noqa: BLE001 - no browser installed
        return False
    return True


needs_playwright = pytest.mark.skipif(not _playwright_ok(), reason="Playwright or Chromium missing")

NOTE = "Client Tan Wei Ming, NRIC S1234567D, age 15, of Oakcrest Secondary School, is doing well."
STATES = {
    "pass": ("PASS: summarise for the case file", "disability"),
    "annotate": ("ANNOTATE: a letter to the day activity centre", "disability"),
    "regenerate": ("REGENERATE: summarise for the case file", "disability"),
    "escalate": ("Email the school principal", "youth-offending"),
}


class _KeyedScreener:
    """The decision follows the first word of the instruction, and youth-offending escalates."""

    def screen(self, draft, pack, seq, instruction="", leaks=None, context="", **kw):
        pid = getattr(pack, "id", pack)
        ev = draft[:60]
        if pid == "youth-offending":
            flags = [
                Flag(
                    label="I14",
                    clause="CYPA 1993 s.111",
                    severity="escalate",
                    evidence=ev,
                    confidence=0.9,
                )
            ]
        elif "REGENERATE" in draft:
            flags = [
                Flag(label="I3", clause="A.7.b", severity="regenerate", evidence=ev, confidence=0.8)
            ]
        elif "ANNOTATE" in draft:
            flags = [
                Flag(
                    label="I10",
                    clause="B.3.a, A.6.d",
                    severity="annotate",
                    evidence=ev,
                    rewrite="She will attend the centre on weekdays.",
                    confidence=0.85,
                ),
                Flag(label="I1", clause="A.7.c", severity="annotate", evidence=ev, confidence=0.6),
            ]
        else:
            return [], "pass", [Screen(seq=seq, flags=[])]
        severity = flags[0].severity
        return flags, severity, [Screen(seq=seq, flags=flags)]


def _app(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    g = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=_KeyedScreener(),
    )
    monkeypatch.setattr(
        "socareguard.proxy.core.complete",
        lambda model, messages, **kw: ("Summary: " + messages[-1]["content"], {}),
    )
    monkeypatch.setattr(appmod, "API_KEYS", set())
    monkeypatch.setattr(appmod, "SUPERVISOR_KEYS", set())
    monkeypatch.setattr(appmod, "SANDBOX", True)
    monkeypatch.chdir(ROOT)
    return appmod.create_app(g)


def _client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    return TestClient(_app(tmp_path, monkeypatch))


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import uvicorn

    mp = pytest.MonkeyPatch()
    app = _app(tmp_path_factory.mktemp("interface"), mp)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(5)
    mp.undo()


def _send(page, base, state):
    instruction, pack = STATES[state]
    page.goto(base + "/")
    page.select_option("#pack", pack)
    page.fill("#instruction", instruction)
    page.fill("#note", NOTE)
    page.click("#send")
    page.wait_for_function(
        "() => (document.getElementById('status').textContent || '').startsWith('Done')"
        " || !document.getElementById('error').hidden",
        timeout=30_000,
    )
    assert page.locator("#error").is_hidden(), page.locator("#error").inner_text()


def _visible_primary(page):
    return page.locator("#result .btn-primary").evaluate_all(
        "els => els.filter(e => e.offsetParent !== null).map(e => e.id + '|' + e.textContent)"
    )


@needs_playwright
@pytest.mark.parametrize("state", list(STATES))
def test_the_banner_shows_one_filled_button_per_state(server, state):
    from playwright.sync_api import sync_playwright

    shots = os.environ.get("SOCAREGUARD_SHOTS")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _send(page, server, state)
        nxt, label = BANNER[state]
        assert page.locator("#decision-next").inner_text() == nxt
        assert _visible_primary(page) == [f"decision-action|{label}"]
        assert page.locator("#decision-title").inner_text().strip()
        # the glossary is inside "More", which starts closed
        assert page.locator("#decision-more").get_attribute("open") is None
        assert page.locator("#glossary").is_hidden()
        assert page.locator("#col-out").is_visible() and page.locator("#col-seen").is_visible()
        assert page.locator("#col-back").is_hidden()
        assert page.locator("#col-back-details").get_attribute("open") is None
        if state == "annotate":
            cards = page.locator("#flags .flag")
            assert cards.count() == 2
            assert cards.nth(0).locator("h3").inner_text() == (
                "Tells the recipient something the client did not agree to share"
            )
            meta = cards.nth(0).locator(".flag-meta").inner_text()
            assert "the screen's own confidence 0.85" in meta and "measured precision" in meta
            assert cards.nth(0).locator("button.accept").inner_text() == "Use this rewrite"
            assert "btn-quiet" in cards.nth(0).locator("form.flag-override summary").get_attribute(
                "class"
            )
            assert "btn-card" in cards.nth(1).locator("form.flag-override summary").get_attribute(
                "class"
            )
            page.click("#decision-action")
            page.wait_for_function(
                "() => document.activeElement && document.activeElement.id === 'flag-0'"
            )
        if state == "escalate":
            assert page.locator("#escalate-note").get_attribute("role") == "alert"
            assert page.locator("#escalate-session #esc-session").is_visible()
        if shots:
            Path(shots).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(shots) / f"banner-{state}.png"), full_page=True)
        browser.close()


@needs_playwright
def test_the_release_needs_the_confirmation(server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _send(page, server, "escalate")
        page.fill("#release-actor", "sup-007")
        page.fill("#release-reason", "Reviewed with the practitioner")
        page.click("#release-form button[type=submit]")
        page.wait_for_selector("#release-confirm:not([hidden])")
        assert page.locator("#release-confirm-who").inner_text() == "sup-007"
        assert page.locator("#release-status").inner_text() == ""
        assert page.locator("#released").is_hidden()
        page.click("#release-confirm-no")
        assert page.locator("#release-confirm").is_hidden()
        assert page.locator("#release-status").inner_text() == ""
        page.click("#release-form button[type=submit]")
        page.click("#release-confirm-yes")
        page.wait_for_function(
            "() => document.getElementById('release-status').textContent.startsWith('Released')"
        )
        assert page.locator("#released").is_visible()
        assert page.locator("#decision-action").inner_text() == "Copy the released draft"
        assert _visible_primary(page) == ["decision-action|Copy the released draft"]
        browser.close()


AXE_JS = os.environ.get("SOCAREGUARD_AXE_JS", "")
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]


def _axe(page, label):
    page.add_script_tag(path=AXE_JS)
    return page.evaluate(
        "tags => axe.run(document, {runOnly: {type: 'tag', values: tags}, resultTypes: ['violations']})"
        ".then(r => ({label: arguments[0], violations: r.violations.map(v => ({id: v.id, impact: v.impact,"
        " nodes: v.nodes.map(n => ({target: n.target, summary: n.failureSummary}))})),"
        " passes: r.passes.map(v => v.id)}))".replace("arguments[0]", json.dumps(label)),
        AXE_TAGS,
    )


@needs_playwright
@pytest.mark.skipif(not (AXE_JS and Path(AXE_JS).is_file()), reason="SOCAREGUARD_AXE_JS not set")
def test_axe_finds_no_contrast_or_target_size_failure(server, tmp_path):
    from playwright.sync_api import sync_playwright

    out = Path(os.environ.get("SOCAREGUARD_AXE_OUT") or tmp_path)
    out.mkdir(parents=True, exist_ok=True)
    runs = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in (1024, 1280):
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.goto(server + "/")
            runs.append(_axe(page, f"compose@{width}"))
            for state in STATES:
                _send(page, server, state)
                # open every disclosure so that the controls inside are measured as well
                page.evaluate(
                    "() => document.querySelectorAll('#result details').forEach(d => d.open = true)"
                )
                if state == "escalate":
                    page.fill("#release-actor", "sup-007")
                    page.fill("#release-reason", "Reviewed with the practitioner")
                    page.click("#release-form button[type=submit]")
                    page.wait_for_selector("#release-confirm:not([hidden])")
                runs.append(_axe(page, f"{state}@{width}"))
                overflow = page.evaluate(
                    "() => document.documentElement.scrollWidth - window.innerWidth"
                )
                assert overflow <= 0, (state, width, overflow)
            page.goto(server + "/supervisor")
            runs.append(_axe(page, f"supervisor-signin@{width}"))
            page.fill("#login-user", "admin")
            page.fill("#login-password", "demo1234")
            page.click("#login-submit")
            page.wait_for_selector("#chain")
            runs.append(_axe(page, f"supervisor@{width}"))
            page.close()
        browser.close()
    (out / "axe-round6-interface.json").write_text(json.dumps(runs, indent=1))
    bad = [
        (r["label"], v["id"], [n["target"] for n in v["nodes"]])
        for r in runs
        for v in r["violations"]
        if v["id"] in ("color-contrast", "target-size")
    ]
    assert not bad, bad
    # both rules ran on every page
    for r in runs:
        assert {"color-contrast", "target-size"} <= set(r["passes"]), r["label"]
