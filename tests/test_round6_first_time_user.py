"""Round 6 first-time-user check: the findings of the round-6 first-time user.

1. A signed-in supervisor releases a withheld draft from the read-only review page: the sign-in
   cookie (or a supervisor key) stands in for the role header and the practitioner's session
   token, and the ledger row names the supervisor. A review token alone, or a practitioner's API
   key, releases nothing.
2 to 7. The column legend is visible by default, the Recipient hint names no flag code, the hint
   of What left the premises says that stand-ins look real by design, the SASW Code is expanded on
   first use, the tool credit sits in a collapsed "About this tool", and the chain check uses
   plain labels.
"""

from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient

from tests.test_round6_supervisor import (
    ORIGINALS,
    STATIC,
    TEMPLATES,
    _app,
    _Doc,
    _login,
    _review,
    _send,
)

REASON = "reviewed%20with%20the%20worker"


def _supervisor_of(page: str):
    m = re.search(r"window\.SOCAREGUARD_SUPERVISOR = (.*?);", page)
    assert m, "the panel does not state the supervisor identity"
    return json.loads(m.group(1))


def _supervisor_client(client):
    """A second browser on the same server: its own cookies, no session token."""
    return TestClient(client.app)


# ---------- 1. release from the review page ----------


def test_a_sandbox_supervisor_releases_from_the_review_page(tmp_path, monkeypatch):
    prac, g = _app(tmp_path, monkeypatch)
    sg = _send(prac)  # youth-offending: escalated and withheld
    assert sg["withheld"]
    sup = _supervisor_client(prac)
    _login(sup)
    assert [q["session"] for q in sup.get("/v1/supervisor/summary").json()["queue"]] == [
        sg["session"]
    ]
    tok = _review(sup, sg["session"])
    # the review page tells the script that the viewer is a signed-in supervisor
    page = sup.get(tok["url"]).text
    assert _supervisor_of(page) == {"actor": "admin (sandbox login)", "attested": False}
    assert _supervisor_of(prac.get(tok["url"]).text) is None
    # the cookie alone: no role header, no session token
    r = sup.get(
        f"/v1/sessions/{sg['session']}/withheld?reason={REASON}",
        headers={"X-SoCareGuard-Review-Token": tok["review_token"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    row = g.ledger.rows()[-1]
    assert row["decision"] == "withheld_released" and row["session"] == sg["session"]
    assert row["actor"] == "admin (sandbox login)" and row["actor_attested"] is False
    assert row["override_reason"] == "reviewed with the worker"
    assert row["request_row_sha256"] == sg["ledger_row_sha256"]
    assert body["ledger_row"]["row_sha256"] == row["row_sha256"]
    # this browser did not create the session: the released draft carries stand-ins only
    assert body["view"] == "pseudonymised" and body["reply"]
    for original in ORIGINALS:
        assert original not in r.text, original
    # the queue on /supervisor empties
    assert sup.get("/v1/supervisor/summary").json()["queue"] == []
    assert 'id="queue-empty"' in sup.get("/supervisor").text


def test_the_practitioners_own_browser_sees_the_restored_release(tmp_path, monkeypatch):
    prac, _ = _app(tmp_path, monkeypatch)
    sg = _send(prac)
    _login(prac)  # the supervisor signs in on the practitioner's own browser
    r = prac.get(
        f"/v1/sessions/{sg['session']}/withheld?reason={REASON}",
        headers={"X-SoCareGuard-Session-Token": sg["session_token"]},
    )
    assert r.status_code == 200
    assert r.json()["view"] == "full"
    assert all(o in r.json()["reply"] for o in ORIGINALS)
    assert r.json()["ledger_row"]["actor"] == "admin (sandbox login)"


def test_a_review_token_alone_cannot_release(tmp_path, monkeypatch):
    prac, g = _app(tmp_path, monkeypatch)
    sg = _send(prac)
    sup = _supervisor_client(prac)
    _login(sup)
    tok = _review(sup, sg["session"])
    stranger = _supervisor_client(prac)  # holds the link, never signed in
    rows = len(g.ledger.rows())
    for headers in (
        {"X-SoCareGuard-Review-Token": tok["review_token"]},
        {"X-SoCareGuard-Review-Token": tok["review_token"], "X-SoCareGuard-Role": "supervisor"},
    ):
        r = stranger.get(f"/v1/sessions/{sg['session']}/withheld?reason={REASON}", headers=headers)
        assert r.status_code == 403, r.text
    assert _supervisor_of(stranger.get(tok["url"]).text) is None
    assert len(g.ledger.rows()) == rows


def test_keyed_mode_needs_the_supervisor_key(tmp_path, monkeypatch):
    prac, _ = _app(tmp_path, monkeypatch, api_keys={"app-key"}, supervisor_keys={"sup-key"})
    sg = _send(prac, key="app-key")
    url = f"/v1/sessions/{sg['session']}/withheld?reason={REASON}"
    practitioner = {
        "Authorization": "Bearer app-key",
        "X-SoCareGuard-Role": "supervisor",
        "X-SoCareGuard-Session-Token": sg["session_token"],
    }
    assert prac.get(url, headers=practitioner).status_code == 403
    # the sandbox login is off, so a login attempt gives no identity either
    _login(prac)
    assert prac.get(url, headers=practitioner).status_code == 403
    sup = _supervisor_client(prac)
    tok = _review(sup, sg["session"], {"Authorization": "Bearer sup-key"})
    rv = {"X-SoCareGuard-Review-Token": tok["review_token"]}
    assert sup.get(url, headers=rv).status_code in (401, 403)  # no key at all
    # a supervisor key alone suffices, and the row is checked by a person
    r = sup.get(url, headers={"Authorization": "Bearer sup-key", "X-SoCareGuard-Actor": "sup-007"})
    assert r.status_code == 200, r.text
    assert r.json()["view"] == "full"
    row = r.json()["ledger_row"]
    assert (row["actor"], row["actor_attested"]) == ("sup-007", True)
    # a key sign-in in the browser does the same from the review page
    sup.post("/supervisor/login", data={"key": "sup-key", "staff_id": "sup-008"})
    assert _supervisor_of(sup.get(tok["url"]).text) == {"actor": "sup-008", "attested": True}
    r = sup.get(url)
    assert r.status_code == 200 and r.json()["ledger_row"]["actor"] == "sup-008"
    assert r.json()["ledger_row"]["actor_attested"] is True


def test_supervisor_keys_alone_refuse_a_self_asserted_release(tmp_path, monkeypatch):
    prac, _ = _app(tmp_path, monkeypatch, supervisor_keys={"sup-key"})
    sg = _send(prac)
    r = prac.get(
        f"/v1/sessions/{sg['session']}/withheld?reason={REASON}",
        headers={"X-SoCareGuard-Role": "supervisor", "X-SoCareGuard-Session-Token": sg["session_token"]},
    )
    assert r.status_code == 403


def test_the_supervisor_json_cannot_close_the_script(tmp_path, monkeypatch):
    prac, _ = _app(tmp_path, monkeypatch, supervisor_keys={"sup-key"})
    prac.post("/supervisor/login", data={"key": "sup-key", "staff_id": "</script><b>x"})
    page = prac.get("/").text
    assert "</script><b>" not in page
    assert _supervisor_of(page)["actor"] == "</script><b>x"


def test_the_review_page_script_shows_the_release_form_to_a_supervisor():
    js = (STATIC / "panel.js").read_text()
    body = js.split("function readOnly(session, full)")[1].split("\n  }\n")[0]
    assert "window.SOCAREGUARD_SUPERVISOR" in body
    assert '$("release").hidden = !canRelease' in body
    assert 'el.closest("#release")' in body
    assert '$("release-actor").readOnly = true' in body
    assert '$("released-note").hidden = data.view !== "pseudonymised"' in js
    # the session token is sent only when this browser holds it
    assert 'if (current.sg.session_token) extra["X-SoCareGuard-Session-Token"]' in js
    html = (TEMPLATES / "panel.html").read_text()
    assert "The practitioner's panel shows the restored draft." in html
    sup = (TEMPLATES / "supervisor.html").read_text()
    assert "Review and release" in sup
    assert "from the release form on the practitioner's panel or through" not in sup


# ---------- 2 to 7 ----------


def _ancestors(doc, id_):
    el = next(e for e in doc.elements if e[1].get("id") == id_)
    return el[2]


def test_the_column_legend_is_visible_by_default(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    doc = _Doc(client.get("/").text)
    assert not any(a[0] == "details" for a in _ancestors(doc, "seen-legend"))
    html = (TEMPLATES / "panel.html").read_text()
    seen = html.split("<h2>What you see</h2>")[1].split("</article>")[0]
    assert "<details" not in seen and "underlined in dots" in seen
    # "More about this result" keeps the glossary and the record summary
    more = html.split('<details id="decision-more">')[1].split("</details>")[0]
    assert 'id="glossary"' in more and 'id="ledgersum"' in more


def test_the_recipient_hint_names_no_flag_code(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    page = client.get("/").text
    hint = page.split('id="audience-hint">')[1].split("</span>")[0]
    assert hint == "Who the draft is for. Some flags depend on it."
    doc = _Doc(page)
    more = next(e for e in doc.elements if e[1].get("id") == "audience-more")
    assert more[0] == "details" and "open" not in more[1]


def test_the_out_hint_says_stand_ins_look_real_by_design():
    html = (TEMPLATES / "panel.html").read_text()
    hint = html.split('id="out-hint">')[1].split("</p>")[0]
    assert hint.startswith("This text went to the model provider.")
    assert "look real by design, so that the model writes naturally" in hint
    assert "every one is invented" in hint


def test_the_sasw_code_is_expanded_on_each_page(tmp_path, monkeypatch):
    full = "Singapore Association of Social Workers Code of Professional Ethics (the SASW Code)"
    client, _ = _app(tmp_path, monkeypatch)
    panel = client.get("/").text
    banner = panel.split('<div class="banner">')[1].split("</div>")[0]
    assert full in banner
    first = panel.find("SASW")
    assert panel[first - len("Professional Ethics (the "): first] == "Professional Ethics (the "
    _login(client)
    _send(client)
    sup = client.get("/supervisor").text
    assert full in sup
    first = sup.find("SASW")
    assert sup[first - len("Professional Ethics (the "): first] == "Professional Ethics (the "


def test_the_tool_credit_is_collapsed_in_about_this_tool(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    page = client.get("/").text
    footer = page.split("<footer>")[1].split("</footer>")[0]
    about = footer.split('<details class="about" id="about-tool">')[1].split("</details>")[0]
    assert "<summary>About this tool</summary>" in about and "LiteLLM" in about
    assert footer.count("LiteLLM") == 1
    assert '<details class="about" id="about-tool" open' not in footer
    # it is the last thing in the footer
    assert footer.rstrip().endswith("</details>")


def test_plain_labels_in_the_chain_check(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    _send(client)
    _login(client)
    page = client.get("/supervisor").text
    chain = page.split('id="chain"')[1].split("</section>")[0]
    for label in ("Rows in the record", "Record fingerprint (head hash)", "Gaps", "no gaps"):
        assert label in chain, label
    assert "The record has not been altered since the last check" in chain
    assert "Chain intact" not in chain and "First gap" not in chain
    js = (STATIC / "panel.js").read_text()
    assert "record not altered, no gaps" in js and "chain intact" not in js.lower()
    # the technical term appears once, in parentheses after the plain words
    assert js.count("quasi-identifier") == 1
    assert "details that identify someone when combined (quasi-identifiers)" in js
    html = (TEMPLATES / "panel.html").read_text()
    assert "record fingerprint (head hash)" in html


def test_stand_ins_are_put_back_in_one_pass():
    """Found in the release check: the age "15" was replaced inside the stand-in NRIC, and the
    generalised age "15 to 17" could be replaced again."""
    from socareguard.proxy.app import _pseudonymise

    pairs = [("Amirul Tan", "Zulkifli"), ("Amirul", "Zul"), ("15", "15 to 17")]
    text = "NRIC T1150755C, age 15, Amirul Tan and AmirulTan"
    assert _pseudonymise(text, pairs) == "NRIC T1150755C, age 15 to 17, Zulkifli and ZulTan"
