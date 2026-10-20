"""The same supervisor path on both sandbox addresses (2026-10-20).

The paper's link (huggingface.co/spaces/kwanhui/socareguard) shows the app in a frame from
another site; the direct address (kwanhui-socareguard.hf.space) shows it as a top-level page. A
reviewer gets the same supervisor path on both: the review page opens in place of the
supervisor view (a new tab out of the frame would lose the partitioned sign-in cookie), and it
shows the stand-in columns, as the paper says ("reviews the stand-in columns"), whichever tab or
frame created the session. The fallback for a dropped cookie shows only when the cookie was
dropped, and no page carries a line that only a framed page shows.
"""

from __future__ import annotations

import re

from tests.test_round6_supervisor import ORIGINALS, STATIC, TEMPLATES, _app, _login, _review, _send

HOST = "kwanhui-socareguard.hf.space"
# What a browser sends for a page inside the Space page's frame, and for the direct address.
FRAMED = {
    "Host": HOST,
    "X-Forwarded-Proto": "https",
    "Sec-Fetch-Dest": "iframe",
    "Sec-Fetch-Site": "cross-site",
    "Referer": "https://huggingface.co/",
}
DIRECT = {"Host": HOST, "X-Forwarded-Proto": "https", "Sec-Fetch-Dest": "document"}


def _function(js: str, name: str) -> str:
    start = js.index(f"async function {name}(")
    end = js.index("\n  }\n", start)
    return js[start:end]


def test_the_supervisor_script_does_not_look_for_a_frame():
    js = (STATIC / "supervisor.js").read_text()
    assert "window.top" not in js and "framed" not in js
    # The review opens in the same tab on both addresses; no new tab and no new-tab link.
    assert "window.location.assign(data.url)" in js
    assert "window.open" not in js and "_blank" not in js


def test_the_supervisor_page_is_the_same_framed_and_direct(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    _send(client)
    for signed_in in (False, True):
        if signed_in:
            _login(client)
        framed = client.get("/supervisor", headers=FRAMED).text
        direct = client.get("/supervisor", headers=DIRECT).text
        assert framed == direct
        assert "framed-only" not in direct and "unframed-only" not in direct
    template = (TEMPLATES / "supervisor.html").read_text()
    assert "framed" not in template.replace("cookie-lost", "")


def test_the_queue_hint_says_the_review_opens_in_place(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    _login(client)
    page = client.get("/supervisor").text
    hint = page[page.index('id="queue-hint"') :]
    hint = hint[: hint.index("</p>")]
    assert "opens in place of this view" in hint and "a link back to this view" in hint
    assert "new tab" not in hint and "this frame" not in hint
    assert "a review opens with stand-ins only" in hint


def test_the_review_page_sends_the_review_token_only():
    js = (STATIC / "panel.js").read_text()
    review = _function(js, "openReview")
    assert '"X-SoCareGuard-Review-Token": review' in review
    assert "X-SoCareGuard-Session-Token" not in review
    assert 'session_token: ""' in review
    # The release from the review page sends the sign-in cookie and the actor, no session token.
    release = js[js.index('$("release-form").addEventListener') :]
    release = release[: release.index("\n  });\n")]
    assert "X-SoCareGuard-Session-Token" not in release
    # A link back to the supervisor view sits in the review note.
    assert 'id="review-back"' in js and 'href="/supervisor"' in js


def test_the_creating_browser_and_another_see_the_same_stand_in_review(tmp_path, monkeypatch):
    """What the review page requests (the cookie and the review token) returns the stand-in
    view, whether or not the tab that asks created the session."""
    client, _ = _app(tmp_path, monkeypatch)
    sg = _send(client)  # this client created the session and holds its token
    _login(client)
    tok = _review(client, sg["session"])
    rv = {"X-SoCareGuard-Review-Token": tok["review_token"]}
    sid = sg["session"]
    session = client.get(f"/v1/sessions/{sid}", headers=rv)
    panel = client.get(f"/v1/sessions/{sid}/panel", headers=rv)
    assert session.status_code == 200 and panel.status_code == 200
    assert session.json()["view"] == "pseudonymised"
    for original in ORIGINALS:
        assert original not in session.text and original not in panel.text
    assert "replacements" not in panel.json()
    # The release from that page (the cookie, the actor, the reason) keeps the stand-ins too.
    rel = client.get(
        f"/v1/sessions/{sid}/withheld?reason=reviewed%20with%20the%20worker",
        headers={**rv, "X-SoCareGuard-Actor": "admin (sandbox login)"},
    )
    assert rel.status_code == 200 and rel.json()["view"] == "pseudonymised"
    for original in ORIGINALS:
        assert original not in rel.text


def test_the_review_note_and_release_note_name_no_browser():
    js = (STATIC / "panel.js").read_text()
    html = (TEMPLATES / "panel.html").read_text()
    assert "did not create the session" not in js and "did not create the session" not in html
    assert re.search(r"with stand-ins only: what left the premises, what the model replied", js)
    assert "Under the shared sandbox login a review never restores the names." in html
