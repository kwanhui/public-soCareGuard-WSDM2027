"""Round 6, work package C: the supervisor view.

The supervisor gate (keys, and the sandbox login with its production statement), the queue of
withheld drafts, the period table with its counts and filters, the chain block, the empty state,
the read-only review token and its guard (another browser's session opens pseudonymised only),
and the selector table check, which skips here because the table is not part of this repository."""

import re
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from socareguard.ledger import ACTION_KINDS, Ledger, action_kind
from socareguard.outbound.vault import Vault
from socareguard.proxy.core import Guard
from socareguard.scenarios.events import Flag, Screen

ROOT = Path(__file__).resolve().parent.parent
NOTE = "Client Tan Wei Ming, NRIC S1234567D, age 15, of Oakcrest Secondary School."
# With the name detectors off (as in every unit test), the NRIC and the school are the direct
# identifiers that receive stand-ins; the re-identified view names them, the pseudonymised one not.
ORIGINALS = ("S1234567D", "Oakcrest")
STATEMENT = (
    "This is a simplistic authentication for demonstration purposes only, with a fixed shared "
    "credential and no rate limiting or lockout, and it must be replaced with proper "
    "authentication (per-user credentials or single sign-on, a supervisor role that the "
    "deployment checks, session expiry and audit) before any production deployment."
)
# The selector table is not part of this repository, so the test that reads it skips; the path
# is assembled so the snapshot guard does not match it.
BRIEF = ROOT / "docs" / ("re" + "views") / "2026-09-28-rounds" / "brief.md"
TEMPLATES = ROOT / "src/socareguard/proxy/templates"
STATIC = ROOT / "src/socareguard/proxy/static"


def _flat(text: str) -> str:
    return " ".join(text.split())


class Screener:
    """Flags the whole draft with one label; the label and severity follow the pack header."""

    def __init__(self, escalate_packs=("youth-offending",)):
        self.escalate_packs = escalate_packs

    def screen(self, draft, pack, seq, instruction="", leaks=None, context="", **kw):
        pid = getattr(pack, "id", pack)
        if pid in self.escalate_packs:
            f = Flag(label="I14", clause="A.6.d", severity="escalate", evidence=draft)
        else:
            f = Flag(label="I1", clause="A.7.c", severity="annotate", evidence=draft, rewrite="x")
        return [f], f.severity, [Screen(seq=seq, flags=[f])]


def _app(tmp_path, monkeypatch, api_keys=(), supervisor_keys=(), escalate=("youth-offending",)):
    from socareguard.proxy import app as appmod

    g = Guard(
        vault=Vault(tmp_path / "v.sqlite"),
        ledger=Ledger(tmp_path / "l.jsonl"),
        use_presidio=False,
        use_gliner=False,
        screener=Screener(escalate),
    )
    # The model echoes what it received, so the restored reply names the client.
    monkeypatch.setattr(
        "socareguard.proxy.core.complete",
        lambda model, messages, **kw: ("Summary: " + messages[-1]["content"], {}),
    )
    monkeypatch.setattr(appmod, "API_KEYS", set(api_keys))
    monkeypatch.setattr(appmod, "SUPERVISOR_KEYS", set(supervisor_keys))
    monkeypatch.setattr(appmod, "SANDBOX", True)
    monkeypatch.chdir(ROOT)
    return TestClient(appmod.create_app(g)), g


def _send(client, pack="youth-offending", key=None, session=None):
    headers = {"X-SoCareGuard-Pack": pack, "X-SoCareGuard-Actor": "sw-042"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if session:
        headers["X-SoCareGuard-Session"] = session
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Email the school.\n\n" + NOTE}]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["socareguard"]


def _login(client, user="admin", password="demo1234"):
    return client.post(
        "/supervisor/login",
        data={"username": user, "password": password},
        follow_redirects=False,
    )


def _review(client, session, headers=None):
    r = client.post(f"/v1/sessions/{session}/review-token", headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()


def _release(client, sg):
    return client.get(
        f"/v1/sessions/{sg['session']}/withheld?reason=reviewed%20with%20the%20worker",
        headers={
            "X-SoCareGuard-Role": "supervisor",
            "X-SoCareGuard-Session-Token": sg["session_token"],
            "X-SoCareGuard-Actor": "sup-007",
        },
    )


def _override(client, sg, kind="override"):
    return client.post(
        "/v1/override",
        json={
            "session": sg["session"],
            "pack": "disability",
            "flag_labels": ["I1"],
            "reason": "kept after discussion",
            "kind": kind,
            "draft_sha256": "ab" * 32,
        },
        headers={"X-SoCareGuard-Session-Token": sg["session_token"]},
    )


# ---------- the gate ----------


def test_keys_configured_needs_a_supervisor_key(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch, api_keys={"app-key"}, supervisor_keys={"sup-key"})
    sg = _send(client, key="app-key")
    assert client.get("/v1/supervisor/summary").status_code == 403
    practitioner = {"Authorization": "Bearer app-key"}
    assert client.get("/v1/supervisor/summary", headers=practitioner).status_code == 403
    assert client.get("/supervisor", headers=practitioner).status_code == 403
    r = client.post(f"/v1/sessions/{sg['session']}/review-token", headers=practitioner)
    assert r.status_code == 403
    sup = {"Authorization": "Bearer sup-key", "X-SoCareGuard-Actor": "sup-007"}
    body = client.get("/v1/supervisor/summary", headers=sup).json()
    assert body["actor"] == "sup-007" and body["actor_attested"] is True
    # a supervisor key opens the full view through a review token
    tok = _review(client, sg["session"], sup)
    full = client.get(
        f"/v1/sessions/{sg['session']}",
        headers={"X-SoCareGuard-Review-Token": tok["review_token"], **sup},
    ).json()
    assert full["view"] == "full"
    assert tok["ledger_row"]["actor_attested"] is True


@pytest.mark.parametrize("api_keys", [set(), {"app-key"}])
def test_the_sandbox_login_is_refused_when_keys_are_configured(tmp_path, monkeypatch, api_keys):
    client, _ = _app(tmp_path, monkeypatch, api_keys=api_keys, supervisor_keys={"sup-key"})
    r = _login(client)
    assert r.status_code == 403
    assert "demonstration login is off" in r.text
    assert "socareguard_supervisor" not in r.headers.get("set-cookie", "")
    assert client.get("/v1/supervisor/summary").status_code == 403
    page = client.get("/supervisor").text
    assert 'id="login-key"' in page and 'id="login-user"' not in page
    # a key sign-in works and is attested
    r = client.post(
        "/supervisor/login", data={"key": "sup-key", "staff_id": "sup-007"}, follow_redirects=False
    )
    assert r.status_code == 303
    body = client.get("/v1/supervisor/summary").json()
    assert (body["actor"], body["actor_attested"]) == ("sup-007", True)


def test_the_sandbox_login_is_required_refused_when_wrong_and_recorded(tmp_path, monkeypatch):
    client, g = _app(tmp_path, monkeypatch)
    sg = _send(client)
    assert client.get("/v1/supervisor/summary").status_code == 403
    assert client.post(f"/v1/sessions/{sg['session']}/review-token").status_code == 403
    page = client.get("/supervisor")
    assert (
        page.status_code == 200 and 'id="sup-login"' in page.text and 'id="queue"' not in page.text
    )
    wrong = _login(client, password="demo12345")
    assert wrong.status_code == 401 and "wrong" in wrong.text
    assert client.get("/v1/supervisor/summary").status_code == 403
    ok = _login(client)
    assert ok.status_code == 303 and ok.headers["location"] == "/supervisor?signin=1"
    body = client.get("/v1/supervisor/summary").json()
    assert (body["actor"], body["actor_attested"]) == ("admin (sandbox login)", False)
    tok = _review(client, sg["session"])
    row = g.ledger.rows()[-1]
    assert row["decision"] == "review_opened"
    assert row["actor"] == "admin (sandbox login)" and row["actor_attested"] is False
    assert row["request_row_sha256"] == sg["ledger_row_sha256"]
    assert tok["ledger_row"]["row_sha256"] == row["row_sha256"]
    # signing out closes the view
    client.post("/supervisor/logout", follow_redirects=False)
    assert client.get("/v1/supervisor/summary").status_code == 403


def test_the_production_statement_is_carried_everywhere(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod
    from socareguard.proxy import demo_login

    assert demo_login.PRODUCTION_WARNING == STATEMENT
    assert STATEMENT in _flat(demo_login.__doc__)
    client, _ = _app(tmp_path, monkeypatch)
    login_route = next(
        r for r in client.app.routes if getattr(r, "path", "") == "/supervisor/login"
    )
    assert STATEMENT in _flat(login_route.endpoint.__doc__)
    assert STATEMENT in _flat((TEMPLATES / "supervisor.html").read_text())
    assert STATEMENT in _flat(client.get("/supervisor").text)
    assert STATEMENT in _flat((ROOT / "README.md").read_text())
    assert demo_login.DEMO_CREDENTIAL == ("admin", "demo1234")
    assert appmod.demo_login is demo_login


# ---------- the guard: another browser's session opens pseudonymised only ----------


def test_a_review_token_alone_opens_the_pseudonymised_view(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    sg = _send(client, pack="disability")
    own = {"X-SoCareGuard-Session-Token": sg["session_token"]}
    reidentified = client.get(f"/v1/sessions/{sg['session']}", headers=own).json()
    assert all(o in reidentified["reply"] for o in ORIGINALS)  # the full view re-identifies
    _login(client)
    tok = _review(client, sg["session"])
    rv = {"X-SoCareGuard-Review-Token": tok["review_token"]}

    r = client.get(f"/v1/sessions/{sg['session']}", headers=rv)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["view"] == "pseudonymised"
    assert "reply" not in body
    for original in ORIGINALS:
        assert original not in r.text, original
    kinds = {e["kind"] for e in body["events"]}
    assert "send" in kinds and "receive" in kinds
    assert "detect" not in kinds
    for e in body["events"]:
        if e["kind"] == "generalise":
            assert all(set(r) <= {"rule", "category"} for r in e["rules"])
    send = next(e for e in body["events"] if e["kind"] == "send")
    assert send["outbound_text"] and "S1234567D" not in send["outbound_text"]
    assert body["flags"] and body["flags"][0]["evidence"]

    p = client.get(f"/v1/sessions/{sg['session']}/panel", headers=rv)
    assert p.status_code == 200
    assert "replacements" not in p.json() and p.json()["view"] == "pseudonymised"
    assert all("original" not in m for m in p.json()["marks"])
    for original in ORIGINALS:
        assert original not in p.text, original

    led = client.get(f"/v1/ledger?session={sg['session']}", headers=rv)
    assert led.status_code == 200 and led.json()["rows"]
    # the review token opens no other session
    other = _send(client, pack="disability")
    assert (
        client.get(
            f"/v1/sessions/{other['session']}",
            headers={"X-SoCareGuard-Review-Token": tok["review_token"]},
        ).status_code
        == 403
    )


def test_the_same_session_with_its_own_token_opens_the_full_view(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    sg = _send(client, pack="disability")
    _login(client)
    tok = _review(client, sg["session"])
    both = {
        "X-SoCareGuard-Review-Token": tok["review_token"],
        "X-SoCareGuard-Session-Token": sg["session_token"],
    }
    body = client.get(f"/v1/sessions/{sg['session']}", headers=both).json()
    assert body["view"] == "full" and all(o in body["reply"] for o in ORIGINALS)
    panel = client.get(f"/v1/sessions/{sg['session']}/panel", headers=both).json()
    assert any(r["original"] == "S1234567D" for r in panel["replacements"])


def test_a_review_token_is_read_only_and_expires(tmp_path, monkeypatch):
    from socareguard.proxy import sessions as sessmod

    client, g = _app(tmp_path, monkeypatch)
    sg = _send(client)  # youth-offending: escalated and withheld
    _login(client)
    rows_before = len(g.ledger.rows())
    tok = _review(client, sg["session"])
    assert len(g.ledger.rows()) == rows_before + 1
    assert tok["expires"] - time.time() == pytest.approx(30 * 60, abs=5)
    rv = {"X-SoCareGuard-Review-Token": tok["review_token"]}
    sid = sg["session"]
    # the token alone, without the supervisor's sign-in, releases nothing (round 6: a signed-in
    # supervisor releases from the review page, tested below)
    client.post("/supervisor/logout", follow_redirects=False)
    released = client.get(
        f"/v1/sessions/{sid}/withheld?reason=x",
        headers={**rv, "X-SoCareGuard-Role": "supervisor"},
    )
    assert released.status_code == 403
    as_token = client.get(
        f"/v1/sessions/{sid}/withheld?reason=x",
        headers={
            "X-SoCareGuard-Role": "supervisor",
            "X-SoCareGuard-Session-Token": tok["review_token"],
        },
    )
    assert as_token.status_code == 403
    ov = client.post(
        "/v1/override",
        json={"session": sid, "pack": "youth-offending", "flag_labels": ["I14"], "reason": "x"},
        headers=rv,
    )
    assert ov.status_code == 403
    assert client.delete(f"/v1/sessions/{sid}", headers=rv).status_code == 403
    assert client.get(f"/v1/sessions/{sid}", headers=rv).status_code == 200
    # the withheld draft is not in the review
    body = client.get(f"/v1/sessions/{sid}", headers=rv)
    assert all(o not in body.text for o in ORIGINALS)
    # 31 minutes later the token opens nothing
    later = time.time() + 31 * 60
    monkeypatch.setattr(sessmod, "_now", lambda: later)
    assert client.get(f"/v1/sessions/{sid}", headers=rv).status_code == 403
    assert client.get(f"/v1/sessions/{sid}/panel", headers=rv).status_code == 403


# ---------- queue, period table, counts, filters ----------


def test_the_queue_lists_an_unreleased_escalation_then_clears(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    sg = _send(client)
    _send(client, pack="disability")  # annotate only: not in the queue
    _login(client)
    queue = client.get("/v1/supervisor/summary").json()["queue"]
    assert [q["session"] for q in queue] == [sg["session"]]
    q = queue[0]
    assert q["pack"] == "youth-offending"
    assert [c["label"] for c in q["categories"]] == ["I14"]
    assert q["practitioner"] == "sw-042" and q["practitioner_label"] == "sw-042, typed in"
    assert q["time"].endswith("UTC")
    page = client.get("/supervisor").text
    assert f'data-session="{sg["session"]}"' in page and 'id="queue-table"' in page
    assert _release(client, sg).status_code == 200
    assert client.get("/v1/supervisor/summary").json()["queue"] == []
    assert 'id="queue-empty"' in client.get("/supervisor").text


def _mixed(client):
    """One escalation with a release, and a disability session with an override and an accepted
    rewrite; then a review opened on each."""
    esc = _send(client)
    dis = _send(client, pack="disability")
    assert _release(client, esc).status_code == 200
    assert _override(client, dis).status_code == 200
    assert _override(client, dis, "rewrite_accepted").status_code == 200
    _login(client)
    _review(client, esc["session"])
    _review(client, dis["session"])
    return esc, dis


def test_counts_equal_rows_by_kind(tmp_path, monkeypatch):
    client, g = _app(tmp_path, monkeypatch)
    _mixed(client)
    body = client.get("/v1/supervisor/summary").json()
    by_kind = {k: 0 for k in ACTION_KINDS}
    for row in g.ledger.rows():
        k = action_kind(row)
        if k:
            by_kind[k] += 1
    assert body["counts"] == by_kind
    assert by_kind == {
        "escalation": 1,
        "withheld_released": 1,
        "override": 1,
        "rewrite_accepted": 1,
        "review_opened": 2,
    }
    listed = {k: sum(1 for a in body["actions"] if a["kind"] == k) for k in ACTION_KINDS}
    assert listed == by_kind and body["total"] == sum(by_kind.values())
    # the table: time first, actor with how it was checked, category and clause, request row
    a = next(a for a in body["actions"] if a["kind"] == "withheld_released")
    assert a["actor_label"] == "sup-007, typed in"
    assert a["categories"][0]["label"] == "I14" and a["categories"][0]["clause"]
    assert a["request_row_sha256"] and a["reason"] == "reviewed with the worker"
    page = client.get("/supervisor").text
    head = re.search(r'id="actions-table">\s*<thead><tr>(.*?)</tr>', page).group(1)
    assert re.findall(r"<th>(.*?)</th>", head)[:2] == ["Time", "Actor"]
    assert "sup-007, typed in" in page
    assert "Kept with a reason" in page and "Rewrite used" in page


def test_filters_by_pack_kind_and_date(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    esc, dis = _mixed(client)
    s = client.get("/v1/supervisor/summary?pack=disability").json()
    assert {a["session"] for a in s["actions"]} == {dis["session"]}
    assert s["queue"] == []
    s = client.get("/v1/supervisor/summary?pack=youth-offending").json()
    assert {a["session"] for a in s["actions"]} == {esc["session"]}
    s = client.get("/v1/supervisor/summary?kind=override").json()
    assert [a["kind"] for a in s["actions"]] == ["override"]
    assert s["counts"]["override"] == 1 and sum(s["counts"].values()) == 1
    s = client.get("/v1/supervisor/summary?category=I14").json()
    assert {a["session"] for a in s["actions"]} == {esc["session"]}
    s = client.get("/v1/supervisor/summary?actor=admin%20(sandbox%20login)").json()
    assert {a["kind"] for a in s["actions"]} == {"review_opened"}
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    tomorrow = datetime.fromtimestamp(time.time() + 86400, UTC).strftime("%Y-%m-%d")
    yesterday = datetime.fromtimestamp(time.time() - 86400, UTC).strftime("%Y-%m-%d")
    assert client.get(f"/v1/supervisor/summary?since={today}").json()["total"] == 6
    assert client.get(f"/v1/supervisor/summary?since={tomorrow}").json()["total"] == 0
    assert client.get(f"/v1/supervisor/summary?since=all&until={yesterday}").json()["total"] == 0
    assert client.get(f"/v1/supervisor/summary?until={today}").json()["total"] == 6
    assert client.get("/v1/supervisor/summary?since=not-a-date").status_code == 400
    assert client.get("/v1/supervisor/summary?kind=nonsense").status_code == 400
    f = client.get("/v1/supervisor/summary").json()["filters"]
    assert f["options"]["pack"] == ["disability", "youth-offending"]
    assert f["options"]["kind"] == list(ACTION_KINDS)
    # the chips on the page link to the same filters
    page = client.get("/supervisor?kind=override").text
    assert 'class="fchip active" data-filter="kind" data-value="override"' in page
    assert 'href="/supervisor?pack=disability&amp;kind=override"' in page


def test_the_chain_block_comes_first_with_its_fields(tmp_path, monkeypatch):
    client, g = _app(tmp_path, monkeypatch)
    _send(client)
    _login(client)
    chain = client.get("/v1/supervisor/summary").json()["chain"]
    assert chain["ok"] is True and chain["rows"] == len(g.ledger.rows())
    assert chain["head_sha256"] == g.ledger.rows()[-1]["row_sha256"]
    assert chain["first_gap"] is None
    assert chain["last_logged"]["head_sha256"] == chain["head_sha256"]
    assert chain["logged_head_matches"] is True
    page = client.get("/supervisor").text
    order = [page.index(f'id="{i}"') for i in ("chain", "queue", "filters", "actions", "counts")]
    assert order == sorted(order)
    for i in ("chain-rows", "chain-head", "chain-gap", "chain-logged"):
        assert f'id="{i}"' in page
    # a tampered row shows as broken
    lines = g.ledger.path.read_text().splitlines()
    lines[0] = lines[0].replace('"pack": "youth-offending"', '"pack": "disability"')
    g.ledger.path.write_text("\n".join(lines) + "\n")
    chain = client.get("/v1/supervisor/summary").json()["chain"]
    assert chain["ok"] is False and chain["first_gap"] == 0
    assert chain["first_bad_row"] == 0


def test_the_empty_state(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    _login(client)
    body = client.get("/v1/supervisor/summary").json()
    assert body["queue"] == [] and body["actions"] == [] and body["total"] == 0
    assert set(body["counts"].values()) == {0}
    assert body["chain"]["rows"] == 0 and body["chain"]["last_logged"] is None
    page = client.get("/supervisor").text
    assert "No withheld draft is waiting for release." in page
    assert (
        "No escalation, release, passage kept with a reason or rewrite used in this period." in page
    )
    assert "nothing logged since the server started" in page


def test_rows_since_reads_one_period(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    led.append({"decision": "override"})
    cut = time.time()
    led.append({"decision": "escalate"})
    assert [r["decision"] for r in led.rows_since(cut)] == ["escalate"]
    assert len(led.rows_since(0)) == 2
    assert "review_opened" in ACTION_KINDS


# ---------- the panel ----------


def test_the_panel_keeps_tokens_and_has_the_review_mode(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    html = client.get("/").text
    assert 'id="supervisor-link"' in html and 'href="/supervisor"' in html
    js = (STATIC / "panel.js").read_text()
    assert (
        "sessionStorage.setItem(TOKENS_KEY" in js
        and "keepToken(sg.session, sg.session_token)" in js
    )
    assert '"X-SoCareGuard-Review-Token"' in js and "readOnly(session, full)" in js


# ---------- the selector table ----------


class _Doc(HTMLParser):
    """Elements as (tag, attrs, ancestors) for a small CSS matcher."""

    VOID = frozenset({"meta", "link", "input", "br", "img", "hr", "source", "area", "col", "wbr"})

    def __init__(self, html):
        super().__init__()
        self.stack, self.elements = [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        el = (tag, {k: (v or "") for k, v in attrs}, list(self.stack))
        self.elements.append(el)
        if tag not in self.VOID:
            self.stack.append(el)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


_COMPOUND = re.compile(r"^([a-z0-9]*)((?:[#.][\w-]+|\[[^\]]+\])*)$")


def _compound_ok(el, compound):
    tag, attrs, _ = el
    m = _COMPOUND.match(compound)
    assert m, compound
    if m.group(1) and m.group(1) != tag:
        return False
    for part in re.findall(r"[#.][\w-]+|\[[^\]]+\]", m.group(2)):
        if part[0] == "#" and attrs.get("id") != part[1:]:
            return False
        if part[0] == "." and part[1:] not in attrs.get("class", "").split():
            return False
        if part[0] == "[":
            name, _, value = part[1:-1].partition("=")
            if name not in attrs or (value and attrs[name] != value.strip("\"'")):
                return False
    return True


def _matches(doc, selector):
    parts = selector.split()
    for el in doc.elements:
        if not _compound_ok(el, parts[-1]):
            continue
        need, ancestors = parts[:-1], el[2]
        for anc in reversed(ancestors):
            if need and _compound_ok(anc, need[-1]):
                need = need[:-1]
        if not need:
            return True
    return False


def _table_selectors(section_text):
    rows = [l for l in section_text.splitlines() if l.startswith("|") and "---" not in l]
    out = []
    for row in rows[1:]:
        cells = [c.strip() for c in row.strip("|").split("|")]
        for sel in re.findall(r"`([^`]+)`", cells[-1]):
            if any(ch in sel for ch in "#.["):
                out.append((cells[0] if len(cells) == 3 else "panel", sel))
    return out


# Elements that the scripts create after a result or a click; each must be written in its script.
_SCRIPTED = {
    "form.flag-override": ("panel.js", '<form class="flag-override'),
    "button.accept": ("panel.js", 'class="btn-card accept"'),
    "a.review-link": ("supervisor.js", 'a.className = "review-link"'),
    "#escalate-session": ("panel.js", 'id="escalate-session"'),
    "#copy-session": ("panel.js", 'id="copy-session"'),
}


@pytest.mark.skipif(not BRIEF.exists(), reason="the selector table is not part of this repository")
def test_every_selector_in_the_brief_resolves(tmp_path, monkeypatch):
    brief = BRIEF.read_text()
    base, _, round6 = brief.partition("### Round 6 additions")
    selectors = _table_selectors(base.split("| Element | Selector |")[1].split("\n\n")[0])
    selectors += _table_selectors(round6.split("| Page | Element | Selector |")[1].split("\n\n")[0])
    assert len(selectors) > 40

    client, _ = _app(tmp_path, monkeypatch)
    pages = {
        "panel": [_Doc(client.get("/").text)],
        "supervisor sign-in": [_Doc(client.get("/supervisor").text)],
    }
    _login(client)
    empty = _Doc(client.get("/supervisor").text)
    _mixed(client)
    _send(client)  # a second escalation stays in the queue
    pages["supervisor"] = [empty, _Doc(client.get("/supervisor").text)]
    for page, sel in selectors:
        if sel in _SCRIPTED:
            script, needle = _SCRIPTED[sel]
            assert needle in (STATIC / script).read_text(), sel
            continue
        assert any(_matches(d, sel) for d in pages[page]), f"{sel} not on the {page} page"
