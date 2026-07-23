"""Keyword dictionaries for demographic estimation (spec section 8).

These signals are matched against an account's OWN public text (bio, display
name, captions, hashtags). They do NOT read individual followers' data.
Extend these lists freely — accuracy improves with vocabulary coverage.
All matching is done in lower-case.
"""
from __future__ import annotations

# --- Gender tendency keywords ---

FEMALE_KEYWORDS: list[str] = [
    # Japanese
    "ママ", "まま", "母", "ママコーデ", "育児", "子育て", "妊娠", "マタニティ",
    "美容", "コスメ", "メイク", "ネイル", "スキンケア", "ファッション", "コーデ",
    "主婦", "ヨガ", "ダイエット", "プチプラ", "女子", "女性", "美肌", "美人",
    "アラサー女子", "スイーツ", "カフェ巡り", "垢抜け", "推し活",
    # English
    "mama", "mom", "mother", "childcare", "beauty", "cosmetics", "cosmetic",
    "makeup", "nail", "skincare", "fashion", "housewife", "yoga", "girl",
    "she/her", "womens", "women's",
]

MALE_KEYWORDS: list[str] = [
    # Japanese
    "パパ", "ぱぱ", "父", "筋トレ", "野球", "サッカー", "メンズファッション",
    "メンズ", "ビジネスマン", "スポーツ", "ジム", "格闘技", "釣り", "車好き",
    "バイク", "ガジェット", "男性", "男子", "副業男子",
    # English
    "father", "dad", "muscle", "workout", "baseball", "football", "soccer",
    "mens fashion", "men's fashion", "businessman", "sports", "gym",
    "he/him", "mens", "men's",
]

# --- Age tendency keywords, mapped to buckets ---

AGE_KEYWORDS: dict[str, list[str]] = {
    "13-17": [
        "高校生", "jk", "女子高生", "男子高校生", "中学生", "10代", "青春",
        "受験生", "high school", "teen", "highschool",
    ],
    "18-24": [
        "大学生", "就活", "大学", "専門学生", "20代前半", "z世代", "新卒",
        "university", "college", "student", "job hunting", "freshman",
    ],
    "25-34": [
        "アラサー", "30代", "20代後半", "社会人", "20代", "働く女性", "os",
        "around 30", "30s", "twenties", "late 20s",
    ],
    "35-44": [
        "アラフォー", "40代", "30代後半", "ワーママ", "働くママ",
        "around 40", "40s", "late 30s",
    ],
    "45-64": [
        "50代", "アラフィフ", "シニア", "60代", "熟年", "セカンドライフ",
        "50s", "60s", "senior", "midlife",
    ],
}
