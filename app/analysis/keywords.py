"""Lexicons and baselines for audience estimation (spec section 8).

Everything here matches an account's OWN public text (bio, display name,
hashtags, captions). Follower-level data is never read — Instagram does not
expose it for third-party accounts.

Scope of this file corresponds to the change list approved by 株式会社ビューズ on
2026-07-30 (改善内容一覧_ASIS-TOBE.xlsx, sheet 4), items 1, 5 and 7.

Why gender is not a word count
------------------------------
An earlier version counted "female words" in the account's text and reported
that as the audience. That measures who the content is ABOUT, which for a
curation account is close to the opposite of who FOLLOWS it. Gender now starts
from a genre base rate and is adjusted per account (see demographics.py).
"""
from __future__ import annotations

# --- Genre -> female share of the AUDIENCE (0.0-1.0) -----------------------
# Approved item 5: expanded 13 -> 24. Ordering no longer decides a match (the
# matcher takes the genre with the MOST keyword hits, approved item 4), but a
# tie is broken by position, so specific genres are listed before general ones.
TOPIC_AUDIENCE: list[tuple[str, list[str], float]] = [
    # --- gaps found during verification of the client's own test accounts ---
    ("ネイル", ["ネイル", "nail", "ジェルネイル", "自爪", "ネイリスト", "ニュアンスネイル",
              "ネイルチップ", "ネイルサロン"], 0.93),
    ("ヘアサロン・美容師", ["美容師", "ヘアサロン", "縮毛矯正", "ヘアカラー", "髪質改善",
                       "ボブ", "白髪", "ヘアスタイル", "カット", "美容室"], 0.80),
    ("整体・治療・健康", ["整体", "鍼灸", "治療院", "施術", "肩こり", "骨盤", "腰痛",
                    "整骨", "セルフケア", "ストレッチ"], 0.62),
    ("ダイエット・ボディメイク", ["ダイエット", "痩せ", "やせ", "リバウンド", "食習慣",
                         "体型", "ボディメイク", "減量"], 0.88),
    # 育児・ママ sits here, ahead of the topic genres, because a tie is broken by
    # position and "who the person IS" must beat "a topic they mention". A
    # frugal-living mother matches ママ once and 節約 once; without this she is
    # classified as ビジネス・副業・マネー (40% female) when she is nearer 88%.
    ("育児・ママ", ["ママ", "育児", "子育て", "マタニティ", "産後", "離乳食",
               "プレママ", "新米ママ", "mama", "maternity"], 0.90),
    # --- the seven genres supplied by the client ---------------------------
    ("ビジネス・副業・マネー", ["副業", "投資", "つみたてnisa", "資産形成", "マネー",
                       "ポイ活", "節約"], 0.40),
    # 暮らす / 住まい / 家づくり added after verification: a bio reading
    # 「心地よく暮らす」 matched nothing, fell through to the captions, and was
    # classified 整体・治療・健康 on one incidental word (59.2% vs 84.6% actual).
    ("暮らし・インテリア", ["インテリア", "部屋作り", "一人暮らし", "ひとり暮らし",
                    "マイホーム", "収納", "100均", "無印良品", "暮らし", "暮らす",
                    "住まい", "家づくり", "間取り", "リノベ", "ルームツアー",
                    "賃貸", "diy", "模様替え"], 0.85),
    ("ペット・動物", ["いぬすたぐらむ", "ねこすたぐらむ", "愛犬", "愛猫", "ペット",
                 "保護猫", "保護犬"], 0.70),
    ("料理・レシピ", ["料理", "レシピ", "おうちごはん", "時短レシピ", "お弁当",
                 "クッキング", "ごはん", "献立"], 0.85),
    ("学び・雑学・資格", ["勉強", "英語", "資格", "雑学", "図解", "自己啓発", "マインド"], 0.50),
    ("イラスト・漫画", ["コミックエッセイ", "絵日記", "イラスト", "あるある", "レポ",
                  "エッセイ"], 0.75),
    ("推し活・エンタメ", ["推し活", "オタ活", "k-pop", "韓流", "アニメ", "参戦服",
                   "ライブ"], 0.85),
    # --- the original thirteen ---------------------------------------------
    ("美容・コスメ", ["コスメ", "美容", "メイク", "スキンケア", "美肌", "垢抜け",
                "cosmetic", "makeup", "skincare", "beauty"], 0.88),
    ("ファッション", ["ファッション", "コーデ", "プチプラ", "着回し", "fashion",
               "outfit", "ootd"], 0.80),
    ("ヨガ・ピラティス", ["ヨガ", "yoga", "ピラティス", "pilates"], 0.78),
    ("グルメ・カフェ", ["グルメ", "カフェ", "スイーツ", "パン", "食べ歩き",
                 "cafe", "sweets", "gourmet"], 0.62),
    ("旅行", ["旅行", "絶景", "観光", "travel", "trip"], 0.55),
    ("フィットネス", ["筋トレ", "フィットネス", "ジム", "workout", "muscle",
              "fitness", "gym"], 0.38),
    ("サーフィン・マリン", ["サーフ", "サーフィン", "サーファー", "波乗り", "surf",
                   "surfing", "マリンスポーツ"], 0.32),
    ("スポーツ観戦", ["野球", "サッカー", "格闘技", "baseball", "soccer",
               "football", "ゴルフ"], 0.25),
    ("ガジェット・カメラ", ["ガジェット", "gadget", "カメラ", "ゲーム", "game"], 0.25),
    ("グラビア・アイドル", ["グラビア", "gravure", "アイドル", "idol", "コスプレ"], 0.20),
    ("車・バイク", ["車好き", "クルマ", "バイク", "car", "motorcycle", "モーター"], 0.15),
    ("釣り・アウトドア", ["釣り", "釣果", "fishing", "キャンプ", "登山"], 0.20),
]

# --- Age baseline patterns (approved item 1) -------------------------------
# Replaces the single global distribution. Percentages are the client's own
# four patterns. Their table stops at "55+"; we carry 55-64 and 65+ separately,
# so that final figure is split 70/30 between them.
AGE_PATTERNS: dict[str, dict[str, float]] = {
    "若年層型": {"13-17": 10.0, "18-24": 35.0, "25-34": 35.0, "35-44": 12.0,
              "45-54": 5.0, "55-64": 2.1, "65+": 0.9},
    "中年層型": {"13-17": 2.0, "18-24": 15.0, "25-34": 45.0, "35-44": 25.0,
              "45-54": 9.0, "55-64": 2.8, "65+": 1.2},
    "趣味型":  {"13-17": 1.0, "18-24": 8.0, "25-34": 25.0, "35-44": 35.0,
              "45-54": 20.0, "55-64": 7.7, "65+": 3.3},
    "全年代型": {"13-17": 5.0, "18-24": 20.0, "25-34": 35.0, "35-44": 22.0,
              "45-54": 12.0, "55-64": 4.2, "65+": 1.8},
}

GENRE_AGE_PATTERN: dict[str, str] = {
    "ネイル": "若年層型", "美容・コスメ": "若年層型", "ファッション": "若年層型",
    "推し活・エンタメ": "若年層型", "グラビア・アイドル": "若年層型",
    "ヘアサロン・美容師": "若年層型",

    "育児・ママ": "中年層型", "料理・レシピ": "中年層型", "暮らし・インテリア": "中年層型",
    "ダイエット・ボディメイク": "中年層型", "イラスト・漫画": "中年層型",
    "ヨガ・ピラティス": "中年層型",

    "車・バイク": "趣味型", "釣り・アウトドア": "趣味型", "ガジェット・カメラ": "趣味型",
    "スポーツ観戦": "趣味型", "サーフィン・マリン": "趣味型", "フィットネス": "趣味型",
    "整体・治療・健康": "趣味型", "ビジネス・副業・マネー": "趣味型",

    "グルメ・カフェ": "全年代型", "旅行": "全年代型", "ペット・動物": "全年代型",
    "学び・雑学・資格": "全年代型",
}
DEFAULT_AGE_PATTERN = "全年代型"

# --- Archetype markers -----------------------------------------------------
SHOWCASE_MARKERS: list[str] = [
    "リポスト", "repost", "ご紹介", "紹介する", "まとめ", "厳選", "コーナー",
    "picks", "セレクト", "特集", "お写真を", "掲載希望", "タグ付け",
    "掲載許可", "図鑑", "カタログ",
]
FEMALE_SUBJECT_MARKERS: list[str] = [
    "美女", "美人", "美少女", "可愛い子", "かわいい子", "girl", "bijo",
    "ゴルフ女子", "筋トレ女子", "サーフ女子", "ヨガ女子",
]
MALE_SUBJECT_MARKERS: list[str] = [
    "イケメン", "美男", "handsome", "男前", "筋肉男子",
]

# --- Creator gender vocabulary (approved item 7) ---------------------------
FEMALE_KEYWORDS: list[str] = [
    "ママ", "まま", "母", "育児", "子育て", "妊娠", "マタニティ", "主婦",
    "女子", "女性", "アラサー女子", "アラフォー女子", "推し活", "わたし", "私",
    "ol", "お姉さん", "娘", "嫁", "奥さん", "妻", "女子大生", "ガール",
    "プレ花嫁", "卒花", "卒花嫁", "プレママ",
    "コスメ", "メイク", "スキンケア", "イエベ", "ブルベ", "骨格診断",
    "骨格ウェーブ", "骨格ストレート", "骨格ナチュラル", "プチプラコーデ",
    "ママコーデ", "フェミニン", "ネイル", "美肌", "垢抜け",
    "mama", "mom", "mother", "she/her", "housewife", "girl", "woman", "female",
]
MALE_KEYWORDS: list[str] = [
    "パパ", "ぱぱ", "父", "旦那", "夫", "息子", "メンズ", "ビジネスマン",
    "男性", "男子", "副業男子", "俺", "僕", "男", "ボーイ",
    "リーマン", "サラリーマン", "お兄さん",
    "メンズ美容", "メンズコスメ", "メンズファッション", "メンズヘア",
    "ヒゲ脱毛", "メンズ脱毛", "新米パパ", "育児パパ", "プレパパ", "筋トレ男子",
    "father", "dad", "he/him", "mens", "men's", "businessman", "boy", "man", "male",
]
# 育児 / 子育て now appear in fathers' profiles too, so a パパ term suppresses the
# female reading rather than both firing at once (client's own note).
MALE_FIRST_MARKERS: list[str] = ["パパ", "ぱぱ", "新米パパ", "育児パパ", "プレパパ"]

# Compound words that CONTAIN a gender character but are themselves neutral.
# They are blanked before gender scoring, otherwise 夫婦 ("married couple")
# registers as 夫 ("husband") — which read a mother's 「共働き夫婦」 as a male
# creator and cost 13 points on one verification account.
NEUTRAL_COMPOUNDS: list[str] = [
    "夫婦", "ご夫婦", "夫妻", "男女", "父母", "祖父母", "両親", "子供", "子ども",
]

# --- Japanese given-name characters (approved item 3, アカウント名 axis) -----
# Separates two accounts in the same genre when the wording does not:
# 莉咲子 -> female, 奨太 -> male.
NAME_FEMALE_CHARS: list[str] = list("子美香奈愛莉咲花恵里菜桜麻沙彩優真結衣乃穂音姫和")
NAME_MALE_CHARS: list[str] = list("郎太朗健翔拓剛男之也雄輝隆哲淳颯悠斗介大樹")

# --- Age vocabulary (approved item 7) --------------------------------------
# NOTE: bare two-digit birth years ("07", "08") were deliberately NOT added.
# They match timestamps, prices and counts, and would reintroduce exactly the
# false-positive problem that item 2 fixes. Only explicitly marked forms are used.
AGE_KEYWORDS: dict[str, list[str]] = {
    "13-17": [
        "高校生", "jk", "ljk", "fjk", "sjk", "女子高生", "男子高校生", "中学生",
        "10代", "青春", "受験生", "部活", "high school", "teen", "highschool",
    ],
    "18-24": [
        "大学生", "就活", "大学", "専門学生", "20代前半", "z世代", "新卒",
        "社会人1年目", "サークル", "university", "college", "student",
        "job hunting", "freshman",
    ],
    "25-34": [
        "アラサー", "30代", "20代後半", "社会人", "20代", "働く女性",
        "around 30", "30s", "twenties", "late 20s",
        "新米ママ", "プレママ", "マタニティ", "妊娠", "産後", "赤ちゃん",
        "ベビー", "離乳食", "新社会人", "プレ花嫁", "0歳", "1歳", "2歳",
        "ol", "maternity", "baby",
    ],
    "35-44": [
        "アラフォー", "40代", "30代後半", "ワーママ", "働くママ",
        "around 40", "40s", "late 30s",
        "小学生", "幼稚園", "保育園", "入学", "習い事", "受験ママ", "主婦",
        "小1", "小2", "小3", "小4", "小5", "小6", "中学生ママ",
    ],
    "45-54": [
        "アラフィフ", "50代", "40代後半", "50s", "midlife",
        "更年期", "セカンドキャリア", "子育て一段落", "高校生ママ",
    ],
    "55-64": [
        "60代", "50代後半", "60s", "熟年", "セカンドライフ", "定年", "還暦",
        "シニア", "senior",
    ],
    "65+": [
        "70代", "70s", "後期高齢", "孫", "孫バカ", "初孫", "年金", "介護",
        "シルバー",
    ],
}
