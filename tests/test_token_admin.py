"""Token store + /admin/token renewal page (behind a login)."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import token_admin, token_store
from app.main import app

TOK = "EAA" + "y" * 120


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "token.json"
    monkeypatch.setattr(token_store, "_path", lambda: path)
    monkeypatch.setattr(token_store, "refresh_expiry", lambda force=False: None)
    token_store.reset_for_tests()
    yield path
    token_store.reset_for_tests()


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(token_admin, "_admin_password", lambda: "secret-pw")
    monkeypatch.setattr(token_admin, "_app_creds", lambda: ("123", "abc"))
    monkeypatch.setattr(token_admin, "_exchange_and_verify",
                        lambda short: ("EAA" + "L" * 120, int(time.time()) + 60 * 86400))
    monkeypatch.setattr(token_admin, "_attempts", {})
    return TestClient(app)


def login(client, password="secret-pw"):
    return client.post("/admin/login", data={"password": password}, follow_redirects=False)


# ---- store -----------------------------------------------------------------

def test_store_persists_and_reloads(store):
    exp = int(time.time()) + 59 * 86400
    assert token_store.set_token("EAA" + "x" * 100, exp) is True
    assert json.loads(store.read_text())["expires_at"] == exp
    token_store.reset_for_tests()               # simulate a restart
    assert token_store.get_token() == "EAA" + "x" * 100
    s = token_store.status()
    assert s["source"] == "file" and s["persisted"] and not s["expired"]
    assert 57 <= s["days_left"] <= 59 and not s["warn"]


def test_status_flags_expiry(store):
    token_store.set_token("EAA" + "x" * 100, int(time.time()) - 10)
    assert token_store.status()["expired"] is True
    token_store.set_token("EAA" + "x" * 100, int(time.time()) + 5 * 86400)
    s = token_store.status()
    assert s["warn"] is True and s["expired"] is False


# ---- login gate ------------------------------------------------------------

def test_page_requires_login(client):
    r = client.get("/admin/token")
    assert r.status_code == 200
    assert "管理者ログイン" in r.text and "更新手順" not in r.text


def test_wrong_password_rejected(client):
    r = login(client, "nope")
    assert r.status_code == 403 and "パスワードが違います" in r.text
    assert "admin_session" not in r.cookies
    assert "更新手順" not in client.get("/admin/token").text


def test_five_failures_block_for_a_minute(client):
    for _ in range(5):
        login(client, "nope")
    r = login(client, "secret-pw")
    assert r.status_code == 429 and "1分" in r.text
    # the lock is per IP: another address is not affected
    other = client.post("/admin/login", data={"password": "secret-pw"},
                        headers={"x-forwarded-for": "203.0.113.9"}, follow_redirects=False)
    assert other.status_code == 303


def test_no_password_configured_refuses(client, monkeypatch):
    monkeypatch.setattr(token_admin, "_admin_password", lambda: "")
    r = login(client, "")
    assert r.status_code == 503 and "ADMIN_PASSWORD" in r.text
    assert "ログインできません" in client.get("/admin/token").text


def test_login_sets_cookie_and_shows_steps(client):
    r = login(client)
    assert r.status_code == 303 and r.headers["location"] == "/admin/token"
    assert "admin_session" in r.cookies
    page = client.get("/admin/token")
    assert "更新手順" in page.text and "グラフAPIエクスプローラ" in page.text
    assert "ログアウト" in page.text and 'name="password"' not in page.text


def test_tampered_or_expired_cookie_rejected(client):
    login(client)
    exp, sig = client.cookies["admin_session"].split(".", 1)
    client.cookies.set("admin_session", str(int(time.time()) - 5) + "." + sig, path="/admin")
    assert "管理者ログイン" in client.get("/admin/token").text
    client.cookies.set("admin_session", exp + "." + "0" * 64, path="/admin")
    assert "管理者ログイン" in client.get("/admin/token").text


def test_logout_clears_session(client):
    login(client)
    r = client.get("/admin/logout", follow_redirects=False)
    assert r.status_code == 303
    assert "管理者ログイン" in client.get("/admin/token").text


# ---- token update ----------------------------------------------------------

def test_token_post_without_login_refused(client):
    r = client.post("/admin/token", data={"token": TOK})
    assert r.status_code == 403 and "ログイン" in r.text
    assert token_store.get_token() != "EAA" + "L" * 120


def test_malformed_token_rejected(client):
    login(client)
    r = client.post("/admin/token", data={"token": "hello"})
    assert r.status_code == 400 and "形式" in r.text


def test_update_swaps_token_and_persists(client, store):
    login(client)
    pasted = "EAA" + "y" * 60 + "\n" + "y" * 60      # line break as pasted from Slack/mail
    r = client.post("/admin/token", data={"token": pasted})
    assert r.status_code == 200 and "トークンを更新しました" in r.text
    assert token_store.get_token() == "EAA" + "L" * 120
    assert store.exists()
    assert "残り 59 日" in r.text or "残り 60 日" in r.text
    assert "EAALLLL" not in r.text                     # never echo the token


def test_exchange_failure_message_is_japanese(client, monkeypatch):
    login(client)

    def boom(short):
        raise token_admin.AdminError("トークンが無効か、期限切れ（発行から1時間）です。")

    monkeypatch.setattr(token_admin, "_exchange_and_verify", boom)
    r = client.post("/admin/token", data={"token": TOK})
    assert r.status_code == 400 and "期限切れ" in r.text


# ---- provider / banner / cold start ----------------------------------------

def test_provider_reads_store_at_call_time(store, monkeypatch):
    import httpx

    from app.providers.graph_api import GraphAPIProvider

    monkeypatch.setattr(token_store, "get_token", lambda: "EAA" + "z" * 100)
    seen = {}

    def fake_get(url, params=None, timeout=None):
        seen["token"] = params["access_token"]
        return httpx.Response(400, json={"error": {"code": 100, "message": "x"}},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    p = object.__new__(GraphAPIProvider)               # skip the .env check in __init__
    p._url = "https://graph.facebook.com/v21.0/1"
    p.last_usage_pct = 0
    with pytest.raises(Exception):
        p.fetch("someone")
    assert seen["token"] == "EAA" + "z" * 100


def test_index_banner_follows_token_status(client, monkeypatch):
    from app import main as main_mod

    monkeypatch.setattr(main_mod, "_token_status", lambda: None)   # mock provider case
    r = client.get("/")
    assert "有効期限" not in r.text                     # no token UI at all

    expired = {"configured": True, "source": "file", "expires_at": 1, "expires_date": "2026/09/20",
               "days_left": -2, "expired": True, "warn": False, "persisted": True}
    monkeypatch.setattr(main_mod, "_token_status", lambda: expired)
    r = client.get("/")
    assert "有効期限が切れています" in r.text and "/admin/token" in r.text

    soon = dict(expired, expired=False, warn=True, days_left=9, expires_date="2026/10/01")
    monkeypatch.setattr(main_mod, "_token_status", lambda: soon)
    r = client.get("/")
    assert "有効期限が近づいています" in r.text and "残り9日" in r.text


def test_request_waits_for_inflight_expiry_check(tmp_path, monkeypatch):
    """Serverless cold start: the warm-up thread is mid-call when the first page
    request arrives. The request must wait for Meta's answer, not show 確認中."""
    import httpx

    monkeypatch.setattr(token_store, "_path", lambda: tmp_path / "token.json")
    token_store.reset_for_tests()
    token_store.set_token("EAA" + "x" * 100, None)          # expiry unknown, like an env token
    exp = int(time.time()) + 50 * 86400

    def slow_get(url, params=None, timeout=None):
        time.sleep(0.3)
        return httpx.Response(200, json={"data": {"is_valid": True, "expires_at": exp}},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", slow_get)
    token_store.warm_up_in_background()
    time.sleep(0.05)                                          # the thread is now inside the call
    token_store.refresh_expiry()                              # request path: must block, then see the value
    assert token_store.status()["expires_at"] == exp
    token_store.reset_for_tests()
