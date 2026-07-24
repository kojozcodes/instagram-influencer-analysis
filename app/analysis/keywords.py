"""Lexicons for audience estimation (spec section 8).

These match an account's OWN public text (bio, display name, captions,
hashtags). They never read individual followers' data.

Why this file is shaped the way it is
-------------------------------------
The first version counted "female words" in the account's text and reported that
as the *audience* gender. That conflates two different things:

    who the content is ABOUT   vs.   who FOLLOWS the account

For a curation account that reposts photos of attractive women, those are close
to opposite. Checked against Instagram's official Insights for two such accounts
the client supplied, the old approach gave 98.6% female where the truth was
59.1%, and 84.4% female where the truth was 14.9%.

So gender is now derived from two separate things:
  1. TOPIC_AUDIENCE  — the audience skew of the subject matter itself
  2. an ARCHETYPE    — whether the account curates images of people (which
                       inverts the pull) or is a creator posting their own life

All matching is lower-cased.
"""
from __future__ import annotations

# --- Topic -> share of the AUDIENCE that is female (0.0-1.0) ---------------
# These are audience skews, not participant skews. Ordered most-specific first;
# the first topic that matches wins.
TOPIC_AUDIENCE: list[tuple[str, list[str], float]] = [
    ("育児・ママ", ["ママ", "育児", "子育て", "マタニティ", "産後", "離乳食",
                  "プレママ", "新米ママ", "mama", "maternity"], 0.90),
    ("美容・コスメ", ["コスメ", "美容", "メイク", "スキンケア", "ネイル", "美肌",
                    "垢抜け", "cosmetic", "makeup", "skincare", "beauty"], 0.88),
    ("ファッション", ["ファッション", "コーデ", "プチプラ", "着回し",
                    "fashion", "outfit", "ootd"], 0.80),
    ("ヨガ・ピラティス", ["ヨガ", "yoga", "ピラティス", "pilates", "ストレッチ"], 0.78),
    ("グルメ・カフェ", ["グルメ", "カフェ", "スイーツ", "パン", "食べ歩き",
                     "cafe", "sweets", "gourmet"], 0.62),
    ("旅行", ["旅行", "絶景", "観光", "travel", "trip"], 0.55),
    ("フィットネス", ["筋トレ", "フィットネス", "ジム", "ボディメイク",
                   "workout", "muscle", "fitness", "gym"], 0.38),
    ("サーフィン・マリン", ["サーフ", "サーフィン", "サーファー", "波乗り",
                        "surf", "surfing", "マリンスポーツ"], 0.32),
    ("スポーツ観戦", ["野球", "サッカー", "格闘技", "baseball", "soccer",
                   "football", "ゴルフ"], 0.25),
    ("ガジェット・カメラ", ["ガジェット", "gadget", "カメラ", "pc", "ゲーム",
                        "game"], 0.25),
    ("グラビア・アイドル", ["グラビア", "gravure", "アイドル", "idol",
                        "コスプレ"], 0.20),
    ("車・バイク", ["車好き", "クルマ", "バイク", "car", "motorcycle",
                 "モーター"], 0.15),
    ("釣り・アウトドア", ["釣り", "釣果", "fishing", "キャンプ", "登山"], 0.20),
]

# --- Archetype markers -----------------------------------------------------
# A "showcase" account curates/reposts other people's photos rather than
# documenting its own life. Its bio typically announces the format.
SHOWCASE_MARKERS: list[str] = [
    "リポスト", "repost", "ご紹介", "紹介する", "まとめ", "厳選", "コーナー",
    "picks", "セレクト", "特集", "お写真を", "掲載希望", "タグ付け",
]

# Who the curated photos are OF. A showcase of women pulls a male audience and
# vice versa — this is the sign that the old model had backwards.
FEMALE_SUBJECT_MARKERS: list[str] = [
    "美女", "美人", "美少女", "可愛い子", "かわいい子", "女子", "girl",
    "bijo", "beauty girl", "女性の",
]
MALE_SUBJECT_MARKERS: list[str] = [
    "イケメン", "美男", "handsome", "男前", "筋肉男子",
]

# --- Creator's own gender (used only for PERSONAL accounts) ----------------
# For a creator posting their own life, the audience tends to align with them.
FEMALE_KEYWORDS: list[str] = [
    "ママ", "まま", "母", "育児", "子育て", "妊娠", "マタニティ", "主婦",
    "女子", "女性", "アラサー女子", "推し活", "わたし", "私",
    "mama", "mom", "mother", "she/her", "housewife",
]
MALE_KEYWORDS: list[str] = [
    "パパ", "ぱぱ", "父", "メンズ", "ビジネスマン", "男性", "男子",
    "副業男子", "俺", "僕",
    "father", "dad", "he/him", "mens", "men's", "businessman",
]

# --- Age tendency keywords, mapped to Instagram's own bands ----------------
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
        "アラサー", "30代", "20代後半", "社会人", "20代", "働く女性",
        "around 30", "30s", "twenties", "late 20s",
        "新米ママ", "プレママ", "マタニティ", "妊娠", "産後", "赤ちゃん",
        "ベビー", "離乳食", "新社会人", "ol", "maternity", "baby",
    ],
    "35-44": [
        "アラフォー", "40代", "30代後半", "ワーママ", "働くママ",
        "around 40", "40s", "late 30s",
        "小学生", "幼稚園", "保育園", "入学", "習い事", "受験ママ", "主婦",
    ],
    "45-54": [
        "アラフィフ", "50代", "40代後半", "50s", "midlife",
        "更年期", "セカンドキャリア",
    ],
    "55-64": [
        "60代", "50代後半", "60s", "熟年", "セカンドライフ", "定年", "還暦",
        "シニア", "senior",
    ],
    "65+": [
        "70代", "70s", "後期高齢", "孫", "年金", "介護", "シルバー",
    ],
}
