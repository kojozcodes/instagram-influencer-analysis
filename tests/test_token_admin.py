"""Token store + /admin/token renewal page."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import token_admin, token_store
from app.main import app


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
    monkeypatch.setattr(token_admin, "_failures", 0)
    monkeypatch.setattr(token_admin, "_blocked_until", 0.0)
    return TestClient(app)


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


def test_page_renders(client):
    r = client.get("/admin/token")
    assert r.status_code == 200
    assert "トークンを更新" in r.text and "グラフAPIエクスプローラ" in r.text


def test_wrong_password_rejected(client):
    r = client.post("/admin/token", data={"password": "nope", "token": "EAA" + "y" * 100})
    assert r.status_code == 403 and "パスワードが違います" in r.text
    assert token_store.get_token() != "EAA" + "L" * 120


def test_five_failures_block_for_a_minute(client):
    for _ in range(5):
        client.post("/admin/token", data={"password": "nope", "token": "EAA" + "y" * 100})
    r = client.post("/admin/token", data={"password": "secret-pw", "token": "EAA" + "y" * 100})
    assert r.status_code == 429 and "1分" in r.text


def test_no_password_configured_refuses(client, monkeypatch):
    monkeypatch.setattr(token_admin, "_admin_password", lambda: "")
    r = client.post("/admin/token", data={"password": "", "token": "EAA" + "y" * 100})
    assert r.status_code == 503 and "ADMIN_PASSWORD" in r.text


def test_malformed_token_rejected(client):
    r = client.post("/admin/token", data={"password": "secret-pw", "token": "hello"})
    assert r.status_code == 400 and "形式" in r.text


def test_update_swaps_token_and_persists(client, store):
    pasted = "EAA" + "y" * 60 + "\n" + "y" * 60      # line break as pasted from Slack/mail
    r = client.post("/admin/token", data={"password": "secret-pw", "token": pasted})
    assert r.status_code == 200 and "トークンを更新しました" in r.text
    assert token_store.get_token() == "EAA" + "L" * 120
    assert store.exists()
    assert "残り 59 日" in r.text or "残り 60 日" in r.text
    assert "EAALLLL" not in r.text                     # never echo the token


def test_exchange_failure_message_is_japanese(client, monkeypatch):
    def boom(short):
        raise token_admin.AdminError("トークンが無効か、期限切れ（発行から1時間）です。")
    monkeypatch.setattr(token_admin, "_exchange_and_verify", boom)
    r = client.post("/admin/token", data={"password": "secret-pw", "token": "EAA" + "y" * 100})
    assert r.status_code == 400 and "期限切れ" in r.text


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
