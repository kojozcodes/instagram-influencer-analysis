from app.analysis.demographics import estimate_demographics
from app.analysis.metrics import calculate_metrics
from app.models import AccountData, Post


def _female_account():
    return AccountData(
        username="yoga_bijo",
        display_name="ヨガ美人｜30代ママ",
        biography="30代ワーママ ヨガとスキンケア #ヨガ #美容 #アラサー #育児",
        followers_count=50000,
        posts=[
            Post(like_count=1000, comments_count=20, caption="#美容 #30代", media_product_type="FEED",
                 permalink="https://insta/p/1", timestamp="2026-07-01T09:00:00+0000"),
            Post(like_count=2000, comments_count=40, caption="#ヨガ #ダイエット", media_product_type="REELS",
                 view_count=50000, permalink="https://insta/p/2", timestamp="2026-06-01T09:00:00+0000"),
        ],
    )


def test_metrics_engagement_and_split():
    m = calculate_metrics(_female_account())
    assert m.avg_likes_30 == 1500.0
    assert m.avg_comments_30 == 30.0
    # (1500 + 30) / 50000 * 100 = 3.06 ; like-only = 1500/50000*100 = 3.0
    assert m.engagement_rate == 3.06
    assert m.like_engagement_rate == 3.0
    # feed split (the FEED post only)
    assert m.feed_avg_likes == 1000.0
    assert m.feed_engagement_rate == 2.04
    # reel split (the REELS post only)
    assert m.reel_avg_likes == 2000.0
    assert m.reel_avg_views == 50000.0
    assert m.reel_engagement_rate == 4.08
    assert m.avg_reels_views == 50000.0


def test_metrics_top_posts_sorted():
    m = calculate_metrics(_female_account())
    # reel (2040 engagement) should rank above feed (1020)
    assert m.top_posts == ["https://insta/p/2", "https://insta/p/1"]


def test_metrics_missing_followers():
    acc = AccountData(username="x", followers_count=None,
                      posts=[Post(like_count=10, comments_count=1, media_product_type="FEED")])
    m = calculate_metrics(acc)
    assert m.engagement_rate is None
    assert m.avg_likes_30 == 10.0


def test_demographics_female_skew():
    d = estimate_demographics(_female_account())
    assert d.female_ratio is not None
    assert d.female_ratio > d.male_ratio
    assert d.classifiable_count > 0
    assert d.analysis_target_count >= d.classifiable_count


def test_demographics_unknown_when_no_signals():
    acc = AccountData(username="blank", biography="", followers_count=100, posts=[])
    d = estimate_demographics(acc)
    assert d.male_ratio is None and d.female_ratio is None
    assert d.classifiable_count == 0
