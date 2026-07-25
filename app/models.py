"""Core data structures shared across the analysis pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Post:
    """A single recent Instagram post."""
    like_count: Optional[int] = None
    comments_count: Optional[int] = None
    caption: str = ""
    media_product_type: str = ""  # e.g. FEED, REELS, IGTV, AD
    view_count: Optional[int] = None  # reels views/plays, if obtainable
    permalink: str = ""
    timestamp: str = ""  # ISO 8601, e.g. 2026-05-01T09:00:00+0000


@dataclass
class AccountData:
    """Raw public data fetched for one Instagram account."""
    username: str
    display_name: str = ""
    account_url: str = ""
    biography: str = ""
    website: str = ""
    followers_count: Optional[int] = None
    media_count: Optional[int] = None
    posts: list[Post] = field(default_factory=list)


class AccountError(Exception):
    """Raised when an account cannot be fetched/analyzed.

    `reason` is a Japanese, user-facing message written into the Excel report.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# --- Analysis result structures ---

# Matches Instagram Insights' own age bands exactly, so estimates can be compared
# to the official figures side by side (the client validates against Insights).
AGE_BUCKETS = ["13-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]


@dataclass
class PostMetrics:
    """Engagement / post metrics (spec F4 + client's エーストリーム column set)."""
    # like-only and overall engagement rate over recent posts (percent)
    like_engagement_rate: Optional[float] = None
    engagement_rate: Optional[float] = None
    # averages over the recent 30 posts
    avg_likes_30: Optional[float] = None
    avg_comments_30: Optional[float] = None
    avg_reels_views: Optional[float] = None
    # feed vs reel split over the recent 12 posts
    feed_avg_likes: Optional[float] = None
    feed_avg_comments: Optional[float] = None
    feed_engagement_rate: Optional[float] = None
    reel_avg_likes: Optional[float] = None
    reel_avg_comments: Optional[float] = None
    reel_engagement_rate: Optional[float] = None
    reel_avg_views: Optional[float] = None
    # top posts by engagement over the last ~6 months (permalinks)
    top_posts: list[str] = field(default_factory=list)


@dataclass
class DemographicsResult:
    male_ratio: Optional[float] = None      # percent
    female_ratio: Optional[float] = None    # percent
    # joint age x gender grid, percent of total audience; keys like "male_25-34"
    grid: dict[str, Optional[float]] = field(default_factory=dict)
    # marginal age distribution. Kept separately from `grid` because the grid is
    # the product of age x gender and therefore collapses to all-None whenever
    # gender is unknown — which would silently discard age we did determine.
    age_ratio: dict[str, Optional[float]] = field(default_factory=dict)
    # True only when the account's own text actually carried age wording. False
    # means age_ratio is a generic assumption, not a reading of this account.
    age_measured_from_text: bool = False
    # age distribution on its own, so age can still be shown when the gender
    # split could not be determined (the grid needs both)
    age_ratio: dict[str, Optional[float]] = field(default_factory=dict)
    analysis_target_count: int = 0
    classifiable_count: int = 0
    unknown_count: int = 0
    # "measured" = Instagram's official follower_demographics (exact, only
    # available for accounts connected to our app); "estimated" = inferred from
    # public text. Shown in the UI/Excel so the two are never confused.
    source: str = "estimated"
    # 高 / 中 / 低 — how much evidence the estimate rests on. Meaningless when
    # source == "measured" (official data is exact), where it is always "実測".
    confidence: str = "低"
    # short human-readable note on what drove the estimate (topic, archetype)
    basis: str = ""


@dataclass
class AnalysisRow:
    """One fully-analyzed account -> one row in the Excel output."""
    username: str
    display_name: str = ""
    account_url: str = ""
    followers_count: Optional[int] = None
    profile_text: str = ""
    demographics: DemographicsResult = field(default_factory=DemographicsResult)
    metrics: PostMetrics = field(default_factory=PostMetrics)
    status: str = "成功"      # 成功 / エラー
    error_reason: str = ""
