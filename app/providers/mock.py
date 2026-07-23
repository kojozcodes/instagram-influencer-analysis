"""Mock provider with fixtures so the full pipeline runs without Meta credentials.

Swapping to the real Graph API is just a PROVIDER=graph change in .env.
Fixtures include a mix of FEED and REELS posts with timestamps so the feed/reel
split, 30-post averages and top-5 (6-month) columns all populate.
"""
from __future__ import annotations

from ..models import AccountData, AccountError, Post


def _posts(spec, handle):
    """spec: list of (kind, likes, comments, views, month) -> Post list.

    kind: 'F' feed / 'R' reel. month: 1-12 (2026). views only used for reels.
    """
    out = []
    for i, (kind, likes, comments, views, month) in enumerate(spec):
        is_reel = kind == "R"
        out.append(Post(
            like_count=likes,
            comments_count=comments,
            caption=f"#サンプル 投稿{i} " + ("#リール" if is_reel else "#フィード"),
            media_product_type="REELS" if is_reel else "FEED",
            view_count=views if is_reel else None,
            permalink=f"https://www.instagram.com/{handle}/p/POST{i:02d}/",
            timestamp=f"2026-{month:02d}-10T09:00:00+0000",
        ))
    return out


_FIXTURES: dict[str, AccountData] = {
    "yoga_bijo": AccountData(
        username="yoga_bijo",
        display_name="ヨガ美人｜30代ママの美容とダイエット",
        account_url="https://www.instagram.com/yoga_bijo",
        biography="30代ワーママ▶ヨガとスキンケアで垢抜け｜美容とダイエット記録 #ヨガ #美容 #アラサー #育児",
        website="https://example.com/yoga_bijo",
        followers_count=48200,
        media_count=312,
        posts=_posts([
            ("F", 1820, 45, None, 7), ("R", 3400, 88, 51000, 7),
            ("F", 2100, 63, None, 6), ("R", 2800, 70, 42000, 6),
            ("F", 1550, 30, None, 5), ("F", 1980, 52, None, 5),
            ("R", 3100, 77, 48000, 4), ("F", 1720, 41, None, 4),
            ("F", 2010, 58, None, 3), ("R", 2600, 66, 39000, 3),
            ("F", 1890, 47, None, 2), ("F", 2200, 61, None, 2),
        ], "yoga_bijo"),
    ),
    "muscle_taro": AccountData(
        username="muscle_taro",
        display_name="筋トレ太郎｜40代パパの肉体改造",
        account_url="https://www.instagram.com/muscle_taro",
        biography="40代パパ｜#筋トレ 歴10年｜野球好き｜メンズファッションも #ジム #スポーツ",
        website="",
        followers_count=15600,
        media_count=540,
        posts=_posts([
            ("F", 620, 18, None, 7), ("R", 900, 30, 12000, 7),
            ("F", 810, 25, None, 6), ("F", 540, 14, None, 6),
            ("R", 760, 22, 9800, 5), ("F", 690, 19, None, 5),
            ("F", 720, 21, None, 4), ("R", 830, 27, 11200, 4),
            ("F", 600, 16, None, 3), ("F", 655, 20, None, 3),
        ], "muscle_taro"),
    ),
    "cafe_days": AccountData(
        username="cafe_days",
        display_name="Cafe Days",
        account_url="https://www.instagram.com/cafe_days",
        biography="日々のカフェ記録｜#カフェ巡り #スイーツ",
        website="",
        followers_count=8300,
        media_count=210,
        posts=_posts([
            ("F", 210, 5, None, 7), ("F", 180, 3, None, 6),
            ("R", 320, 8, 5200, 6), ("F", 240, 6, None, 5),
            ("F", 195, 4, None, 4), ("F", 205, 5, None, 3),
        ], "cafe_days"),
    ),
    "private_account": None,   # type: ignore[assignment]
    "nonexistent_user": None,  # type: ignore[assignment]
}


class MockProvider:
    def fetch(self, username: str) -> AccountData:
        key = username.lower()
        if key == "private_account":
            raise AccountError("非公開アカウントのため取得できません")
        if key not in _FIXTURES or _FIXTURES[key] is None:
            raise AccountError("アカウントが存在しないか、取得できません")
        return _FIXTURES[key]
