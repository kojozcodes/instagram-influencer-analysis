"""Real Instagram Graph API provider using the business_discovery endpoint.

business_discovery lets our own connected IG Business/Creator account look up
PUBLIC Business/Creator accounts by username and read profile + recent media
(likes/comments). It does NOT expose follower demographics or personal accounts
— which is exactly why demographics are estimated (spec F5).

Requires (see .env):
  - IG_USER_ID:        our own connected IG Business account id
  - GRAPH_ACCESS_TOKEN: long-lived token (instagram_basic + pages_show_list)

This class is only imported when PROVIDER=graph, so the app runs without httpx
credentials during development.
"""
from __future__ import annotations

import json

import httpx

from ..config import settings
from ..models import AccountData, AccountError, Post

_GRAPH_BASE = "https://graph.facebook.com"


class GraphAPIProvider:
    def __init__(self) -> None:
        if not settings.ig_user_id or not settings.graph_access_token:
            raise RuntimeError(
                "PROVIDER=graph requires IG_USER_ID and GRAPH_ACCESS_TOKEN in .env"
            )
        self._url = f"{_GRAPH_BASE}/{settings.graph_api_version}/{settings.ig_user_id}"
        # Highest percentage Meta reported via x-app-usage (0-100). The whole
        # system shares one quota, so CachingProvider reads this to throttle.
        self.last_usage_pct: int = 0

    def _record_usage(self, resp: httpx.Response) -> None:
        """Track Meta's reported quota consumption from the x-app-usage header."""
        raw = resp.headers.get("x-app-usage")
        if not raw:
            return
        try:
            usage = json.loads(raw)
        except ValueError:
            return
        # total_time is typically the binding metric, but take the worst.
        self.last_usage_pct = max(
            int(usage.get("call_count", 0) or 0),
            int(usage.get("total_cputime", 0) or 0),
            int(usage.get("total_time", 0) or 0),
        )

    def _media_fields(self) -> str:
        limit = settings.recent_posts_limit
        return (
            f"media.limit({limit})"
            "{caption,like_count,comments_count,media_product_type,permalink,timestamp}"
        )

    def fetch(self, username: str) -> AccountData:
        fields = (
            f"business_discovery.username({username})"
            "{username,name,followers_count,media_count,biography,website,"
            f"{self._media_fields()}}}"
        )
        params = {"fields": fields, "access_token": settings.graph_access_token}

        try:
            resp = httpx.get(self._url, params=params, timeout=30.0)
        except httpx.RequestError as exc:  # network/timeout
            raise AccountError(f"外部アクセスエラー: {exc.__class__.__name__}") from exc

        self._record_usage(resp)

        if resp.status_code != 200:
            raise AccountError(self._map_error(resp))

        data = resp.json().get("business_discovery")
        if not data:
            raise AccountError("アカウント情報が取得できません")

        return self._to_account_data(username, data)

    @staticmethod
    def _map_error(resp: httpx.Response) -> str:
        """Translate a Graph API error payload into a Japanese reason.

        Excel error reasons must ALWAYS be Japanese — never Meta's raw English.
        """
        try:
            err = resp.json().get("error", {})
        except ValueError:
            return f"APIエラー (HTTP {resp.status_code})"
        message = (err.get("message") or "").lower()
        code = err.get("code")

        # Known business_discovery failure modes -> our own wording.
        if code in (110, 803) or "does not exist" in message or "cannot be found" in message \
                or "invalid user" in message:
            return "アカウントが存在しないか、ビジネス/クリエイターアカウントではありません"
        if "not a business" in message or "media_business" in message:
            return "対象がビジネス/クリエイターアカウントではないため取得できません"
        if "private" in message:
            return "非公開アカウントのため取得できません"
        if code in (4, 17, 32) or "limit" in message:
            return "API制限に達しました。時間をおいて再実行してください"
        if code == 190:
            return "アクセストークンが無効です（設定を確認してください）"

        # Meta sometimes supplies its OWN localized message — prefer it over the
        # raw English "message" field so nothing English leaks into the Excel.
        localized = err.get("error_user_msg") or err.get("error_user_title")
        if localized:
            return localized
        return f"分析に失敗しました（APIエラー コード{code or resp.status_code}）"

    @staticmethod
    def _to_account_data(username: str, data: dict) -> AccountData:
        media = (data.get("media") or {}).get("data", [])
        posts = [
            Post(
                like_count=m.get("like_count"),
                comments_count=m.get("comments_count"),
                caption=m.get("caption", "") or "",
                media_product_type=m.get("media_product_type", "") or "",
                permalink=m.get("permalink", "") or "",
                timestamp=m.get("timestamp", "") or "",
            )
            for m in media
        ]
        return AccountData(
            username=data.get("username", username),
            display_name=data.get("name", "") or "",
            account_url=f"https://www.instagram.com/{data.get('username', username)}",
            biography=data.get("biography", "") or "",
            website=data.get("website", "") or "",
            followers_count=data.get("followers_count"),
            media_count=data.get("media_count"),
            posts=posts,
        )
