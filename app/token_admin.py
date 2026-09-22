"""Self-service token renewal page (/admin/token).

The client pastes the short-lived token from the Graph API Explorer; the server
exchanges it for a 60-day token with the app secret, verifies it, and swaps it
into token_store. No redeploy, no relay through the developers.

Protected by ADMIN_PASSWORD (env). Without it the page refuses to accept tokens.
"""
from __future__ import annotations

import hmac
import threading
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import token_store
from .config import settings

router = APIRouter()
_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_GRAPH = "https://graph.facebook.com"
REQUIRED_SCOPES = ("pages_show_list", "instagram_basic",
                   "instagram_manage_insights", "pages_read_engagement")

# brute-force brake: after 5 wrong passwords, refuse for 60 s (per process)
_fail_lock = threading.Lock()
_failures = 0
_blocked_until = 0.0


class AdminError(Exception):
    """Message shown to the user (Japanese)."""


def _admin_password() -> str:
    return settings.admin_password


def _app_creds() -> tuple[str, str]:
    return settings.graph_app_id, settings.graph_app_secret


def _check_password(given: str) -> None:
    global _failures, _blocked_until
    expected = _admin_password()
    if not expected:
        raise AdminError("管理パスワード（ADMIN_PASSWORD）がサーバーに設定されていないため、"
                         "この画面からは更新できません。開発者にご連絡ください。")
    with _fail_lock:
        if time.time() < _blocked_until:
            raise AdminError("パスワードの誤りが続いたため、1分ほど待ってからやり直してください。")
        if not hmac.compare_digest(given.encode(), expected.encode()):
            _failures += 1
            if _failures >= 5:
                _failures = 0
                _blocked_until = time.time() + 60
            raise AdminError("パスワードが違います。")
        _failures = 0


def _exchange_and_verify(short_token: str) -> tuple[str, int | None]:
    """short-lived token -> (60-day token, expires_at). Raises AdminError in Japanese."""
    app_id, app_secret = _app_creds()
    if not app_id or not app_secret:
        raise AdminError("アプリの設定（GRAPH_APP_ID / GRAPH_APP_SECRET）がサーバーにありません。"
                         "開発者にご連絡ください。")
    ver = settings.graph_api_version
    try:
        r = httpx.get(f"{_GRAPH}/{ver}/oauth/access_token", params={
            "grant_type": "fb_exchange_token", "client_id": app_id,
            "client_secret": app_secret, "fb_exchange_token": short_token}, timeout=30.0)
    except httpx.HTTPError:
        raise AdminError("Facebookに接続できませんでした。少し待ってからやり直してください。")
    if r.status_code != 200:
        raise AdminError("トークンが無効か、期限切れ（発行から1時間）です。"
                         "手順1〜4をもう一度行い、新しいトークンを貼り付けてください。")
    long_token = r.json().get("access_token", "")
    if not long_token:
        raise AdminError("Facebookからトークンを受け取れませんでした。もう一度お試しください。")

    # what did we get? expiry + permissions
    try:
        d = httpx.get(f"{_GRAPH}/{ver}/debug_token", params={
            "input_token": long_token, "access_token": long_token},
            timeout=30.0).json().get("data", {})
    except (httpx.HTTPError, ValueError):
        d = {}
    if d.get("is_valid") is False:
        raise AdminError("受け取ったトークンが無効です。手順1〜4をもう一度行ってください。")
    scopes = set(d.get("scopes") or [])
    missing = [s for s in REQUIRED_SCOPES if scopes and s not in scopes]
    if missing:
        raise AdminError("権限が不足しています：" + "、".join(missing)
                         + "。手順2で4つの権限がすべて選ばれているか確認してください。")
    exp = d.get("expires_at")
    expires_at = exp if isinstance(exp, int) and exp > 0 else None

    # prove it can read our own IG account (what every analysis call needs)
    if settings.ig_user_id:
        try:
            v = httpx.get(f"{_GRAPH}/{ver}/{settings.ig_user_id}", params={
                "fields": "username", "access_token": long_token}, timeout=30.0)
        except httpx.HTTPError:
            raise AdminError("Facebookに接続できませんでした。少し待ってからやり直してください。")
        if v.status_code != 200:
            raise AdminError("このトークンではInstagramアカウントを読み取れません。"
                             "手順3で「allmine」ページとInstagramアカウントを選んだか確認してください。")
    return long_token, expires_at


def _render(request: Request, status_code: int = 200, **extra):
    ctx = {"request": request, "token_status": token_store.status(),
           "password_configured": bool(_admin_password()), "app_id": settings.graph_app_id}
    ctx.update(extra)
    return _templates.TemplateResponse("admin_token.html", ctx, status_code=status_code)


@router.get("/admin/token", response_class=HTMLResponse)
def token_page(request: Request):
    token_store.refresh_expiry()
    return _render(request)


@router.post("/admin/token", response_class=HTMLResponse)
def token_update(request: Request, password: str = Form(""), token: str = Form("")):
    try:
        _check_password(password)
    except AdminError as e:
        code = 503 if not _admin_password() else (429 if "1分" in str(e) else 403)
        return _render(request, status_code=code, error=str(e))

    token = "".join(token.split())  # pasted tokens often carry line breaks
    if not token.startswith("EAA") or len(token) < 50:
        return _render(request, status_code=400,
                       error="トークンの形式が正しくありません。「アクセストークン」欄の文字列を"
                             "そのまま貼り付けてください。")
    try:
        long_token, expires_at = _exchange_and_verify(token)
    except AdminError as e:
        return _render(request, status_code=400, error=str(e))

    persisted = token_store.set_token(long_token, expires_at)
    return _render(request, success=True, persisted=persisted)
