"""The supervisor sign-in inside the Hugging Face Space page's frame.

The Space page frames the app from another site (hf.space), so the supervisor cookie is
SameSite=None, Secure and Partitioned over https, and SameSite=Lax over plain http (local runs).
Relaxing SameSite drops the protection that Strict gave against cross-site requests, so every
request that changes state with the cookie is refused when its Origin (or Referer) is another
site. A sign-in that the browser did not keep shows a message instead of the bare form."""

from fastapi.testclient import TestClient

from tests.test_round6_supervisor import _app, _login, _send

HOST = "kwanhui-socareguard.hf.space"
SAME = {"Origin": f"https://{HOST}", "X-Forwarded-Proto": "https", "Host": HOST}
EVIL = {"Origin": "https://evil.example", "X-Forwarded-Proto": "https", "Host": HOST}


def _https_client(tmp_path, monkeypatch, **kw):
    client, g = _app(tmp_path, monkeypatch, **kw)
    return TestClient(client.app, base_url=f"https://{HOST}"), g


def _attrs(set_cookie: str) -> set[str]:
    return {p.strip().lower() for p in set_cookie.split(";")[1:]}


def test_the_cookie_is_samesite_none_secure_partitioned_behind_https(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    r = client.post(
        "/supervisor/login",
        data={"username": "admin", "password": "demo1234"},
        headers={"X-Forwarded-Proto": "https"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    attrs = _attrs(r.headers["set-cookie"])
    assert {"httponly", "secure", "samesite=none", "partitioned", "path=/"} <= attrs
    out = client.post(
        "/supervisor/logout", headers={"X-Forwarded-Proto": "https"}, follow_redirects=False
    )
    cleared = _attrs(out.headers["set-cookie"])
    assert {"httponly", "secure", "samesite=none", "partitioned", "path=/", "max-age=0"} <= cleared


def test_the_cookie_is_lax_without_secure_over_plain_http(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    attrs = _attrs(_login(client).headers["set-cookie"])
    assert "samesite=lax" in attrs and "secure" not in attrs and "partitioned" not in attrs
    assert client.get("/v1/supervisor/summary").status_code == 200


def test_the_cookie_secure_setting_overrides_the_scheme(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    client, _ = _app(tmp_path, monkeypatch)
    monkeypatch.setattr(appmod, "COOKIE_SECURE", "1")
    assert "partitioned" in _attrs(_login(client).headers["set-cookie"])
    monkeypatch.setattr(appmod, "COOKIE_SECURE", "0")
    r = client.post(
        "/supervisor/login",
        data={"username": "admin", "password": "demo1234"},
        headers={"X-Forwarded-Proto": "https"},
        follow_redirects=False,
    )
    assert "samesite=lax" in _attrs(r.headers["set-cookie"])


def test_a_same_origin_sign_in_and_release_are_accepted(tmp_path, monkeypatch):
    client, g = _https_client(tmp_path, monkeypatch)
    sg = _send(client)
    r = client.post(
        "/supervisor/login",
        data={"username": "admin", "password": "demo1234"},
        headers=SAME,
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/supervisor?signin=1"
    page = client.get("/supervisor?signin=1", headers=SAME)
    assert 'id="sup-who"' in page.text and 'id="cookie-lost"' not in page.text
    tok = client.post(f"/v1/sessions/{sg['session']}/review-token", headers=SAME)
    assert tok.status_code == 200
    rel = client.get(f"/v1/sessions/{sg['session']}/withheld?reason=checked", headers=SAME)
    assert rel.status_code == 200 and g.ledger.rows()[-1]["decision"] == "withheld_released"
    # A Referer of this app counts as the same origin when Origin is absent.
    ref = {"Referer": f"https://{HOST}/supervisor", "Host": HOST}
    assert client.post(f"/v1/sessions/{sg['session']}/review-token", headers=ref).status_code == 200


def test_a_forwarded_host_or_an_allowed_origin_is_accepted(tmp_path, monkeypatch):
    from socareguard.proxy import app as appmod

    client, _ = _app(tmp_path, monkeypatch)
    sg = _send(client)
    _login(client)
    url = f"/v1/sessions/{sg['session']}/review-token"
    fwd = {"Origin": f"https://{HOST}", "X-Forwarded-Host": HOST}
    assert client.post(url, headers=fwd).status_code == 200
    other = {"Origin": "https://agency.example"}
    assert client.post(url, headers=other).status_code == 403
    monkeypatch.setattr(appmod, "ALLOWED_ORIGINS", {"https://agency.example"})
    assert client.post(url, headers=other).status_code == 200


def test_cross_origin_requests_with_the_cookie_are_refused(tmp_path, monkeypatch):
    client, g = _https_client(tmp_path, monkeypatch)
    sg = _send(client)
    _login(client)
    rows = len(g.ledger.rows())
    sid = sg["session"]
    for method, url in (
        ("post", f"/v1/sessions/{sid}/review-token"),
        ("get", f"/v1/sessions/{sid}/withheld?reason=forged"),
        ("post", "/supervisor/logout"),
        ("delete", f"/v1/sessions/{sid}"),
    ):
        r = getattr(client, method)(url, headers=EVIL, follow_redirects=False)
        assert r.status_code == 403 and "cross-origin" in r.text, (method, url, r.text)
    # A Referer of another site, a null Origin and Sec-Fetch-Site: cross-site are refused too.
    url = f"/v1/sessions/{sid}/review-token"
    assert client.post(url, headers={"Referer": "https://evil.example/x"}).status_code == 403
    assert client.post(url, headers={"Origin": "null"}).status_code == 403
    assert client.post(url, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert len(g.ledger.rows()) == rows
    # The sign-in still holds: the refused logout did not end it.
    assert client.get("/v1/supervisor/summary", headers=SAME).status_code == 200
    # Reading is not refused: a cross-site page cannot read the response without CORS.
    assert client.get("/v1/supervisor/summary", headers=EVIL).status_code == 200


def test_a_cross_origin_sign_in_is_refused(tmp_path, monkeypatch):
    client, _ = _https_client(tmp_path, monkeypatch)
    r = client.post(
        "/supervisor/login",
        data={"username": "admin", "password": "demo1234"},
        headers=EVIL,
        follow_redirects=False,
    )
    assert r.status_code == 403 and "set-cookie" not in r.headers


def test_an_api_key_request_is_not_checked_for_its_origin(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch, api_keys=("k1",), supervisor_keys=("sup",))
    sg = _send(client, key="k1")
    client.cookies.set("socareguard_supervisor", "anything")
    r = client.post(
        f"/v1/sessions/{sg['session']}/review-token",
        headers={"Authorization": "Bearer sup", "Origin": "https://evil.example"},
    )
    assert r.status_code == 200


def test_a_sign_in_that_did_not_stick_shows_a_message(tmp_path, monkeypatch):
    client, _ = _app(tmp_path, monkeypatch)
    page = client.get("/supervisor?signin=1")
    assert page.status_code == 200 and 'id="sup-login"' in page.text
    assert 'id="cookie-lost"' in page.text and "did not keep the sign-in cookie" in page.text
    assert 'href="/supervisor" target="_blank" rel="noopener"' in page.text
    assert "Open the supervisor view in a new tab" in page.text
    plain = client.get("/supervisor")
    assert 'id="cookie-lost"' not in plain.text
    # The framed line is in both pages, hidden until the script finds the page framed.
    assert 'class="summary framed-only" id="framed-note" hidden' in plain.text
    _login(client)
    signed = client.get("/supervisor")
    assert 'id="sup-who"' in signed.text and 'id="framed-note" hidden' in signed.text
    assert "Open the supervisor view in a new tab" in signed.text
