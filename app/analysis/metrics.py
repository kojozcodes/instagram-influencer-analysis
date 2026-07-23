"""Post-based metrics: engagement, feed/reel split, averages, top posts.

Matches the client's エーストリーム reference columns (F4 + additions). Only
obtainable values are used; anything missing stays None (blank in Excel).
Reel view counts in particular may be unavailable for third-party accounts via
the official API — those come back None.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import AccountData, PostMetrics, Post

RECENT_N = 30      # averages over recent 30 posts
SPLIT_N = 12       # feed/reel split over recent 12 posts
TOP_K = 5          # number of top posts
TOP_MONTHS = 6     # top posts over the last ~6 months


def _avg(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _is_reel(p: Post) -> bool:
    return (p.media_product_type or "").upper() == "REELS"


def _rate(likes: float | None, comments: float | None, followers: int | None) -> float | None:
    if not followers or followers <= 0:
        return None
    if likes is None and comments is None:
        return None
    return round(((likes or 0.0) + (comments or 0.0)) / followers * 100, 2)


def _parse_ts(ts: str):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(ts[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def calculate_metrics(account: AccountData) -> PostMetrics:
    posts = account.posts
    followers = account.followers_count
    m = PostMetrics()

    # --- averages over recent 30 ---
    recent = posts[:RECENT_N]
    likes30 = [p.like_count for p in recent if p.like_count is not None]
    comments30 = [p.comments_count for p in recent if p.comments_count is not None]
    m.avg_likes_30 = _avg(likes30)
    m.avg_comments_30 = _avg(comments30)
    reel_views = [p.view_count for p in recent if _is_reel(p) and p.view_count is not None]
    m.avg_reels_views = _avg(reel_views)

    if followers and followers > 0 and m.avg_likes_30 is not None:
        m.like_engagement_rate = round(m.avg_likes_30 / followers * 100, 2)
    m.engagement_rate = _rate(m.avg_likes_30, m.avg_comments_30, followers)

    # --- feed vs reel split over recent 12 ---
    split = posts[:SPLIT_N]
    feed = [p for p in split if not _is_reel(p)]
    reel = [p for p in split if _is_reel(p)]
    m.feed_avg_likes = _avg([p.like_count for p in feed if p.like_count is not None])
    m.feed_avg_comments = _avg([p.comments_count for p in feed if p.comments_count is not None])
    m.feed_engagement_rate = _rate(m.feed_avg_likes, m.feed_avg_comments, followers)
    m.reel_avg_likes = _avg([p.like_count for p in reel if p.like_count is not None])
    m.reel_avg_comments = _avg([p.comments_count for p in reel if p.comments_count is not None])
    m.reel_avg_views = _avg([p.view_count for p in reel if p.view_count is not None])
    m.reel_engagement_rate = _rate(m.reel_avg_likes, m.reel_avg_comments, followers)

    # --- top posts by engagement over the last ~6 months ---
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=TOP_MONTHS * 31)
    candidates = []
    for p in posts:
        t = _parse_ts(p.timestamp)
        if t is not None and t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        # include posts within the window, or those with no timestamp
        if t is None or t >= cutoff:
            engagement = (p.like_count or 0) + (p.comments_count or 0)
            candidates.append((engagement, p))
    candidates.sort(key=lambda x: x[0], reverse=True)
    m.top_posts = [p.permalink for _, p in candidates[:TOP_K] if p.permalink]

    return m
