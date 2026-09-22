"""Runtime store for the Meta access token.

Until now the token lived only in the environment (GRAPH_ACCESS_TOKEN), so every
60-day renewal meant editing .env / the host's env vars and restarting. This
module lets the token be replaced while the app runs (see token_admin.py) and,
where the disk is writable (VPS), keeps it across restarts.

Precedence at startup: token file (newest) > GRAPH_ACCESS_TOKEN env.
On serverless hosts the file may not be writable; the new token then lives in
memory until the next cold start, and the env var remains the fallback.

Nothing here ever logs or prints a token.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import settings

_JST = timezone(timedelta(hours=9))
_lock = threading.Lock()
_refresh_lock = threading.Lock()  # one Meta round-trip at a time
_EXPIRY_RECHECK_SECONDS = 3600  # ask Meta for the expiry at most hourly
_EXPIRY_RETRY_SECONDS = 300     # ...but retry sooner after a failed attempt


@dataclass
class TokenRecord:
    access_token: str = ""
    expires_at: int | None = None  # unix seconds (UTC); None = not known yet
    updated_at: int | None = None
    source: str = "none"           # "file" | "env" | "admin" | "none"
    checked_at: float = 0.0        # last time expires_at was confirmed with Meta


_rec: TokenRecord | None = None


def _path() -> Path:
    if settings.token_store_path:
        return Path(settings.token_store_path)
    return settings.project_root / "data" / "token.json"


def _load() -> TokenRecord:
    p = _path()
    try:
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("access_token"):
                return TokenRecord(
                    access_token=d["access_token"],
                    expires_at=d.get("expires_at"),
                    updated_at=d.get("updated_at"),
                    source="file",
                )
    except (OSError, ValueError):
        pass
    if settings.graph_access_token:
        return TokenRecord(access_token=settings.graph_access_token, source="env")
    return TokenRecord()


def _record() -> TokenRecord:
    global _rec
    if _rec is None:
        with _lock:
            if _rec is None:
                _rec = _load()
    return _rec


def get_token() -> str:
    """The token every Graph API call must use (read at call time, never cached by callers)."""
    return _record().access_token


def _persist(rec: TokenRecord) -> bool:
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"access_token": rec.access_token, "expires_at": rec.expires_at,
                        "updated_at": rec.updated_at}),
            encoding="utf-8",
        )
        os.replace(tmp, p)
        return True
    except OSError:
        return False


def set_token(token: str, expires_at: int | None) -> bool:
    """Swap in a new token immediately for all requests; persist when possible.

    Returns True when the token was written to disk (survives restarts)."""
    global _rec
    rec = TokenRecord(access_token=token, expires_at=expires_at,
                      updated_at=int(time.time()), source="admin", checked_at=time.time())
    with _lock:
        _rec = rec
    return _persist(rec)


def refresh_expiry(force: bool = False) -> None:
    """Learn/confirm the expiry from Meta's debug_token (hourly at most).

    Needed for tokens that came from the environment, whose expiry we were never
    told. Serialized: while one caller (e.g. the start-up thread) is waiting on
    Meta, a concurrent page request waits for that answer instead of showing
    「確認中」. Best-effort: any failure leaves the record unchanged and is
    retried after 5 minutes, a successful answer after an hour."""
    rec = _record()
    if not rec.access_token:
        return
    with _refresh_lock:
        if not force and time.time() - rec.checked_at < _EXPIRY_RECHECK_SECONDS:
            return
        try:
            import httpx

            resp = httpx.get(
                f"https://graph.facebook.com/{settings.graph_api_version}/debug_token",
                params={"input_token": rec.access_token, "access_token": rec.access_token},
                timeout=10.0,  # a cold call can take ~6 s
            )
            data = resp.json().get("data", {})
        except Exception:  # network, timeout, bad JSON: keep what we have
            data = {}
        if not data:
            rec.checked_at = time.time() - _EXPIRY_RECHECK_SECONDS + _EXPIRY_RETRY_SECONDS
            return
        rec.checked_at = time.time()
        if data.get("is_valid") is False:
            rec.expires_at = int(time.time()) - 1  # mark expired so the UI can say so
            return
        exp = data.get("expires_at")
        if isinstance(exp, int) and exp > 0:
            rec.expires_at = exp
            if rec.source == "file":
                _persist(rec)


def warm_up_in_background() -> None:
    """Learn the expiry before the first page is served (fire-and-forget)."""
    threading.Thread(target=refresh_expiry, kwargs={"force": True}, daemon=True).start()


def status() -> dict:
    """What the UI shows: expiry in JST, days left, whether it is persisted."""
    rec = _record()
    now = time.time()
    if rec.expires_at is None:
        days_left = None
        expired = False
    else:
        days_left = int((rec.expires_at - now) // 86400)
        expired = rec.expires_at <= now
    return {
        "configured": bool(rec.access_token),
        "source": rec.source,
        "expires_at": rec.expires_at,
        "expires_date": (datetime.fromtimestamp(rec.expires_at, _JST).strftime("%Y/%m/%d")
                         if rec.expires_at else None),
        "days_left": days_left,
        "expired": expired,
        "warn": (not expired) and days_left is not None and days_left <= 14,
        "persisted": rec.source == "file" or (rec.source == "admin" and _path().exists()),
    }


def reset_for_tests() -> None:
    global _rec
    with _lock:
        _rec = None
