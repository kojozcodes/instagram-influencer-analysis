"""Lexicons, genre table and baselines for audience estimation (spec section 8).

Everything here matches an account's OWN public text (bio, display name,
hashtags, captions). Follower-level data is never read — Instagram does not
expose it for third-party accounts.

Implements the batch approved by 株式会社ビューズ on 2026-08-03: the 28-genre
structure, weighted scoring, AND-conditions, negative keywords, the メンズ
override and the reverse-pattern (exposure) markers.

Two decisions carried out as instructed:
  * Our own calibrated genre ratios are kept wherever we have measured evidence
    for them. The proposed reductions (整体 62→55, フィットネス 38→30,
    ダイエット 88→85) are NOT applied — testing showed 3 of 4 accounts got worse.
  * The メンズ override reads profile text and display name ONLY, never hashtags:
    one #メンズギフト among 138 tags would otherwise cut a 84.9%-female account
    by 40-50 points.

Note on vocabulary: the client's 28-genre table gives 主な判定語彙（イメージ）—
samples, not the full database. Detailed 強/中/弱 lists were supplied for 14
genres in 精度２.docx; the remainder are filled from those samples plus the
vocabulary already in use here. Any list can be extended without code changes.
"""
from __future__ import annotations

# --- Genre table -----------------------------------------------------------
# (name, female_ratio, {"s": strong 3.0, "m": medium 2.0, "w": weak 1.0}, age_pattern)
#
# Scoring: score = 3.0*strong_hits + 2.0*medium_hits + 1.0*weak_hits.
# Highest score wins; a tie keeps the earlier entry, so identity-defining
# genres are listed before topic genres (a frugal-living mother must not be
# classified as ビジネス on the single word 節約).
GENRES: list[tuple[str, float, dict[str, list[str]], str]] = [
    ("ネイル", 0.93, {
        "s": ["ネイリスト", "ネイルサロン", "自爪育成", "ネイルチップ", "ネイル"],
        "m": ["ジェルネイル", "ニュアンスネイル", "フィルイン", "爪育", "nail", "nails"],
        "w": ["美爪"],
    }, "若年層型"),
    ("ヘアサロン・美容師", 0.80, {
        "s": ["美容師", "スタイリスト", "理容師", "表参道美容師", "美容室"],
        "m": ["縮毛矯正", "髪質改善", "レイヤーカット", "ボブ", "白髪ぼかし",
              "ハイライト", "インナーカラー", "ヘアサロン", "ヘアカラー"],
        "w": ["艶髪", "前髪", "ヘアスタイル"],
    }, "若年層型"),
    ("エステ・脱毛・美容医療", 0.88, {
        "s": ["エステティシャン", "美容外科", "美容皮膚科"],
        "m": ["ダーマペン", "ポテンツァ", "脱毛", "ハイフ", "医療脱毛", "エステ"],
        "w": ["小顔", "毛穴"],
    }, "若年層型"),
    ("整体・治療・健康", 0.62, {   # ours, not the proposed 0.55
        "s": ["整体師", "鍼灸師", "柔道整復師", "治療院", "整骨院"],
        "m": ["骨盤矯正", "小顔矯正", "産後整体", "鍼灸", "整骨", "肩こり",
              "腰痛", "整体"],
        "w": ["姿勢改善", "セルフケア", "ストレッチ"],
    }, "趣味型"),
    ("ダイエット・ボディメイク", 0.88, {   # ours, not the proposed 0.85
        "s": ["ダイエッター", "宅トレダイエッター"],
        "m": ["宅トレ", "痩せる", "リバウンド", "食事制限", "体型公開",
              "pfcバランス", "ダイエット", "ボディメイク", "減量"],
        "w": ["痩せたい", "脚痩せ", "痩せ", "やせ", "食習慣", "体型"],
    }, "中年層型"),
    ("育児・ワンオペ・プレママ", 0.90, {   # ours, not the proposed 0.95
        "s": ["プレママ", "新米ママ", "ワンオペママ", "育休", "保活"],
        "m": ["育児", "子育て", "マタニティ", "産後", "離乳食", "0歳ママ",
              "ママ", "mama", "maternity"],
        "w": ["ベビー", "赤ちゃん"],
    }, "中年層型"),
    ("子育て・キッズ（小〜中学生）", 0.85, {
        "s": ["小1の壁", "中学受験", "スポ少", "受験ママ"],
        "m": ["小学生", "幼稚園", "保育園", "習い事", "中学生ママ", "学童"],
        "w": ["入学", "運動会"],
    }, "中年層型"),
    ("美容・コスメ", 0.88, {
        "s": ["コスメ好き", "コスメオタク", "メイク講師"],
        "m": ["cosmetic", "cosmetics", "makeup", "skincare", "デパコス",
              "プチプラコスメ", "メガ割", "qoo10", "ベスコス", "韓国コスメ",
              "パーソナルカラー", "イエベ", "ブルベ", "コスメ", "スキンケア"],
        "w": ["垢抜け", "肌荒れ", "美容", "メイク", "美肌"],
    }, "若年層型"),
    ("ファッション（レディース・総合）", 0.80, {
        "s": ["アパレル店員", "アパレルデザイナー", "淡色女子"],
        "m": ["fashion", "outfit", "ootd", "grl", "gu", "ユニクロ", "uniqlo",
              "shein", "zara", "しまむら", "骨格ウェーブ", "骨格ストレート",
              "淡色コーデ", "低身長コーデ", "着回し"],
        "w": ["プチプラ", "コーデ", "ファッション"],
    }, "若年層型"),
    ("ファッション（メンズ）", 0.15, {
        "s": ["古着男子", "メンズファッション", "メンズコーデ"],
        "m": ["ストリート", "メンズ古着", "メンズスタイル"],
        "w": ["古着"],
    }, "若年層型"),
    ("推し活・オタ活", 0.85, {   # ours, not the proposed 0.90
        "s": ["推し活", "オタ活", "痛バッグ"],
        "m": ["参戦服", "概念コーデ", "メンカラ", "k-pop", "韓流", "アニメ"],
        "w": ["推し", "ライブ"],
    }, "若年層型"),
    ("ヨガ・ピラティス", 0.78, {   # ours; the proposed 0.90 breaks yoga_bijo
        "s": ["ヨガインストラクター", "ピラティスインストラクター"],
        "m": ["マシンピラティス", "ピラティス", "pilates", "ヨガ", "yoga"],
        "w": ["ストレッチ", "柔軟"],
    }, "中年層型"),
    ("料理・レシピ", 0.85, {
        "s": ["管理栄養士", "料理研究家", "料理家", "フードコーディネーター"],
        "m": ["レシピ", "おうちごはん", "時短レシピ", "お弁当", "献立",
              "作り置き", "クッキング"],
        "w": ["料理", "ごはん", "簡単"],
    }, "中年層型"),
    ("グルメ・カフェ・スイーツ", 0.62, {   # ours, not the proposed 0.65
        "s": ["カフェ巡り", "グルメ巡り", "スイーツ巡り"],
        "m": ["東京グルメ", "食べ歩き", "スイーツ", "パンケーキ", "cafe",
              "sweets", "gourmet"],
        "w": ["カフェ", "グルメ", "パン"],
    }, "全年代型"),
    ("ラーメン・居酒屋・男飯", 0.30, {
        "s": ["ラーメンスタグラム", "街中華", "ハシゴ酒", "男飯"],
        "m": ["ラーメン", "居酒屋", "二郎", "せんべろ", "餃子"],
        "w": ["飲み"],
    }, "趣味型"),
    ("暮らし・インテリア", 0.85, {
        "s": ["インテリアコーディネーター", "一人暮らし女子"],
        "m": ["部屋作り", "マイホーム", "収納", "100均", "無印良品", "ダイソー",
              "セリア", "ikea", "ニトリ", "楽天room", "room", "インテリア",
              "リノベ", "賃貸", "暮らす", "住まい", "家づくり"],
        "w": ["丁寧な暮らし", "暮らし", "ズボラ"],
    }, "中年層型"),
    ("DIY・賃貸リノベ", 0.45, {
        "s": ["賃貸diy", "リノベーション"],
        "m": ["100均diy", "diy", "セルフリノベ", "工具"],
        "w": ["日曜大工"],
    }, "趣味型"),
    ("ポイ活・節約・家計管理", 0.75, {
        "s": ["家計簿アカウント", "家計管理初心者", "ポイ活"],
        "m": ["家計簿", "やりくり", "積立nisa", "nisa", "つみたてnisa",
              "投資信託", "ポン活", "ウエル活", "楽天経済圏"],
        "w": ["貯金", "お得"],
    }, "中年層型"),
    ("投資・副業・ビジネス", 0.25, {
        "s": ["投資家", "起業家", "アフィリエイター"],
        "m": ["fx", "株式投資", "暗号資産", "仮想通貨", "不動産投資", "物販",
              "せどり", "アフィリエイト", "sns運用", "脱サラ", "fire"],
        "w": ["副業", "収益化", "投資"],
    }, "趣味型"),
    ("フィットネス・筋トレ", 0.38, {   # ours, not the proposed 0.30
        "s": ["パーソナルトレーナー", "トレーニー"],
        "m": ["筋トレ", "エニタイム", "ベンチプレス", "フィジーク", "増量期",
              "プロテイン", "ワークアウト", "workout", "fitness", "gym"],
        "w": ["バルクアップ", "ジム"],
    }, "趣味型"),
    ("スポーツ観戦（女子向け）", 0.60, {
        "s": ["bリーグ女子", "観戦女子"],
        "m": ["bリーグ", "フィギュアスケート", "観戦コーデ", "ダンマク"],
        "w": ["応援"],
    }, "全年代型"),
    ("スポーツ観戦（男子向け・競技）", 0.20, {
        "s": ["プロゴルファー", "格闘家"],
        "m": ["野球", "サッカー", "格闘技", "100切り", "rizin",
              "ブレイキングダウン", "baseball", "ゴルフ"],
        "w": ["観戦"],
    }, "趣味型"),
    ("アウトドア（ファミキャン・おでかけ）", 0.55, {
        "s": ["ファミリーキャンパー"],
        "m": ["ファミリーキャンプ", "グランピング", "キャンプ飯",
              "子連れキャンプ", "キャンピングカー"],
        "w": ["おでかけ", "キャンプ"],
    }, "全年代型"),
    ("アウトドア（釣り・ソロキャン）", 0.15, {
        "s": ["アングラー", "ソロキャンパー"],
        "m": ["釣果", "ショアジギング", "ブッシュクラフト", "ソロキャン",
              "無骨キャンプ", "fishing", "釣り"],
        "w": ["釣行", "登山"],
    }, "趣味型"),
    ("旅行・観光・ホテル", 0.55, {   # ours, not the proposed 0.70
        "s": ["旅女", "タビジョ", "ホテルステイ"],
        "m": ["旅行", "絶景", "観光", "ホテル", "travel", "trip"],
        "w": ["旅"],
    }, "全年代型"),
    ("ペット（犬・猫）", 0.70, {
        "s": ["いぬのいる暮らし", "ねこのいる暮らし", "保護猫", "保護犬",
              "犬のいる暮らし", "猫のいる暮らし"],
        "m": ["いぬすたぐらむ", "ねこすたぐらむ", "愛犬", "愛猫", "柴犬", "豆柴",
              "トイプードル", "チワワ", "チャウチャウ", "ポメラニアン",
              "ダックス", "コーギー", "フレブル", "ゴールデンレトリバー",
              "パピヨン", "シュナウザー", "犬", "猫"],
        "w": ["ペット", "わんこ", "にゃんこ", "いぬ", "ねこ"],
    }, "全年代型"),
    ("ガジェット・PC・家電", 0.25, {   # ours, not the proposed 0.20
        "s": ["デスク周り", "自作pc", "apple信者"],
        "m": ["ガジェット", "gadget", "ipad活用", "カメラ", "ゲーム"],
        "w": ["家電"],
    }, "趣味型"),
    ("車・バイク・モータースポーツ", 0.15, {
        "s": ["バイク女子", "愛車撮影"],
        "m": ["クルマ", "バイク", "car", "motorcycle", "モーター", "ドライブ"],
        "w": ["車好き"],
    }, "趣味型"),
    ("イラスト・漫画", 0.75, {
        "s": ["コミックエッセイ", "絵日記"],
        "m": ["イラスト", "エッセイ", "漫画"],
        "w": ["あるある", "レポ"],
    }, "中年層型"),
    ("学び・雑学・資格", 0.50, {
        "s": ["資格取得", "英語学習"],
        "m": ["勉強", "英語", "資格", "雑学", "図解", "自己啓発"],
        "w": ["マインド"],
    }, "全年代型"),
    ("サーフィン・マリン", 0.32, {
        "s": ["サーファー", "波乗り"],
        "m": ["サーフィン", "surf", "surfing", "マリンスポーツ", "サーフ"],
        "w": ["海"],
    }, "趣味型"),
    ("グラビア・アイドル", 0.20, {
        "s": ["グラビア", "gravure", "アイドル", "idol"],
        "m": ["コスプレ", "写真集", "撮影会"],
        "w": ["被写体"],
    }, "若年層型"),
]

# --- AND-conditions --------------------------------------------------------
# A word too ambiguous to score alone. 節約 appears in both a frugal mother's
# profile and an investment account's; on its own it misclassified ラッコママ様
# as ビジネス (40% female) when she is 88%.
# (trigger, partners, genre, weight)
AND_RULES: list[tuple[str, list[str], str, float]] = [
    ("節約", ["主婦", "ママ", "ポイ活", "家計", "やりくり", "献立"],
     "ポイ活・節約・家計管理", 3.0),
    ("節約", ["副業", "投資", "fire", "資産形成", "せどり", "物販"],
     "投資・副業・ビジネス", 3.0),
]
# Words that never score on their own, only through AND_RULES above.
AND_ONLY_WORDS: list[str] = ["節約"]

# --- Negative keywords -----------------------------------------------------
# Presence of these suppresses the genre even if its own words matched.
NEGATIVE_KEYWORDS: dict[str, list[str]] = {
    "ヘアサロン・美容師": ["メンズ専門"],
    "ダイエット・ボディメイク": ["増量", "バルクアップ"],
    "美容・コスメ": ["メンズ美容", "メンズコスメ"],
}

# --- メンズ override -------------------------------------------------------
# Applied to PROFILE TEXT and DISPLAY NAME ONLY — never hashtags. One
# #メンズギフト among 138 tags would otherwise cut とらりんか様 (84.9% female)
# by 40-50 points.
MENS_MARKERS: list[str] = [
    "メンズ", "メンズ専門", "古着男子", "メンズ美容", "メンズコスメ",
    "メンズカット", "メンズヘア", "メンズファッション", "男の", "mens",
]
MENS_OVERRIDE_SHIFT = -1.90   # log-odds; about -40pt near a 0.88 base
MENS_FLOOR = 0.10             # never below 10% female

# --- Reverse-pattern (exposure / fan-service) markers ----------------------
# Approved item 2. A female creator whose content sells on her appearance draws
# a predominantly male audience — the inversion seen on 長谷川真美様 (25.1%
# female actual, we said 91.4%) and 世手子様 (28.6% actual, we said 70.7%).
# Text and hashtags only; no image analysis in this batch.
EXPOSURE_TAGS: list[str] = [
    "水着", "ビキニ", "bikini", "グラビア", "gravure", "ランジェリー", "下着",
    "撮影会", "チェキ", "写真集", "ポートレート", "被写体", "サロンモデル",
    "レースクイーン", "コスプレ", "セクシー",
]
PERFORMER_MARKERS: list[str] = [
    "シンガー", "歌手", "アーティスト", "アイドル", "タレント",
    "ソングライター", "ワンマン", "デビュー", "モデル", "女優",
]
# Applied only when the account is NOT already male-leaning.
EXPOSURE_SHIFT_STRONG = -1.30   # explicit exposure wording present
EXPOSURE_SHIFT_WEAK = -0.55     # performer/model framing only

# --- Age baseline patterns -------------------------------------------------
# The client's four patterns. Their table stops at "55+", which we split 70/30
# across 55-64 and 65+.
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
DEFAULT_AGE_PATTERN = "全年代型"

# --- まとめ型 (curation) ---------------------------------------------------
SHOWCASE_MARKERS: list[str] = [
    "リポスト", "repost", "ご紹介", "紹介する", "まとめ", "厳選", "コーナー",
    "picks", "セレクト", "特集", "お写真を", "掲載希望", "タグ付け",
    "掲載許可", "図鑑", "カタログ", "保存版", "保存必須", "徹底比較",
    "徹底解説", "ランキング", "まとめ記事", "買ってよかった",
]
# In captions these appear on ordinary personal posts too, so a frequency
# threshold applies there (approved: 20% of recent posts).
SHOWCASE_CAPTION_THRESHOLD = 0.20
FEMALE_SUBJECT_MARKERS: list[str] = [
    "美女", "美人", "美少女", "可愛い子", "かわいい子", "girl", "bijo",
    "ゴルフ女子", "筋トレ女子", "サーフ女子", "ヨガ女子", "美女図鑑",
    "美脚", "サロンモデル", "被写体モデル", "ポートレートモデル",
]
MALE_SUBJECT_MARKERS: list[str] = [
    "イケメン", "美男", "handsome", "男前", "筋肉男子", "イケメン図鑑",
    "メンズモデル", "黒髪男子", "韓国男子", "マッシュ男子",
]

# --- Creator gender vocabulary ---------------------------------------------
FEMALE_KEYWORDS: list[str] = [
    "ママ", "まま", "母", "育児", "子育て", "妊娠", "マタニティ", "主婦",
    "女子", "女性", "アラサー女子", "アラフォー女子", "推し活", "わたし", "私",
    "ol", "お姉さん", "娘", "嫁", "奥さん", "妻", "女子大生", "ガール",
    "プレ花嫁", "卒花", "卒花嫁", "プレママ", "女の子ママ", "姉妹ママ",
    "ワンオペママ", "アラサーol", "コスメ", "メイク", "スキンケア",
    "イエベ", "ブルベ", "イエベ春", "イエベ秋", "ブルベ夏", "ブルベ冬",
    "骨格診断", "骨格ウェーブ", "骨格ストレート", "骨格ナチュラル",
    "プチプラコーデ", "ママコーデ", "フェミニン", "ネイル", "美肌", "垢抜け",
    "mama", "mom", "mother", "she/her", "housewife", "girl", "woman", "female",
]
MALE_KEYWORDS: list[str] = [
    "パパ", "ぱぱ", "父", "旦那", "夫", "息子", "メンズ", "ビジネスマン",
    "男性", "男子", "副業男子", "俺", "僕", "男", "ボーイ",
    "リーマン", "サラリーマン", "お兄さん", "男飯", "筋トレパパ",
    "男の身だしなみ", "メンズ美容", "メンズコスメ", "メンズファッション",
    "メンズヘア", "ヒゲ脱毛", "メンズ脱毛", "新米パパ", "育児パパ",
    "プレパパ", "筋トレ男子", "脱サラ",
    "father", "dad", "he/him", "mens", "men's", "businessman", "boy", "man", "male",
]
MALE_FIRST_MARKERS: list[str] = ["パパ", "ぱぱ", "新米パパ", "育児パパ", "プレパパ",
                                 "筋トレパパ"]
# Compounds containing a gendered substring but referring to both/neither.
NEUTRAL_COMPOUNDS: list[str] = [
    "夫婦", "夫妻", "男女", "父母", "両親", "子供", "子ども", "兄妹", "姉弟",
]

NAME_FEMALE_CHARS: list[str] = list("子美香奈愛莉咲花恵里菜桜麻沙彩優真結衣乃穂音姫和")
NAME_MALE_CHARS: list[str] = list("郎太朗健翔拓剛男之也雄輝隆哲淳颯悠斗介大樹")

# --- Age vocabulary --------------------------------------------------------
# Bare two-digit birth years ("07", "08") are deliberately excluded: they match
# timestamps, prices and counts, reintroducing the false positives that the
# age-range fix removed.
AGE_KEYWORDS: dict[str, list[str]] = {
    "13-17": [
        "高校生", "jk", "ljk", "fjk", "sjk", "女子高生", "男子高校生", "中学生",
        "10代", "青春", "受験生", "部活", "high school", "teen", "highschool",
    ],
    "18-24": [
        "大学生", "就活", "大学", "専門学生", "20代前半", "z世代", "新卒",
        "社会人1年目", "サークル", "ガクチカ", "23卒", "24卒", "25卒", "26卒",
        "一人暮らし初心者", "university", "college", "student", "freshman",
    ],
    "25-34": [
        "アラサー", "30代", "20代後半", "社会人", "20代", "働く女性",
        "around 30", "30s", "twenties", "late 20s",
        "新米ママ", "プレママ", "マタニティ", "妊娠", "産後", "赤ちゃん",
        "ベビー", "離乳食", "新社会人", "プレ花嫁", "プレ花", "生後",
        "0歳", "1歳", "2歳", "育休", "育休復帰", "保活", "ol", "maternity",
    ],
    "35-44": [
        "アラフォー", "40代", "30代後半", "ワーママ", "働くママ",
        "around 40", "40s", "late 30s",
        "小学生", "幼稚園", "保育園", "入学", "習い事", "受験ママ", "主婦",
        "小1", "小2", "小3", "小4", "小5", "小6", "小学校", "小1の壁",
        "中学受験", "スポ少", "中学生ママ",
    ],
    "45-54": [
        "アラフィフ", "50代", "40代後半", "50s", "midlife",
        "更年期", "セカンドキャリア", "子育て一段落", "高校生ママ",
        "大学受験", "子離れ", "夫婦二人暮らし",
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

# Backwards-compatible view used by older callers/tests.
TOPIC_AUDIENCE: list[tuple[str, list[str], float]] = [
    (name, kw["s"] + kw["m"] + kw["w"], ratio) for name, ratio, kw, _ in GENRES
]
GENRE_AGE_PATTERN: dict[str, str] = {name: pat for name, _, _, pat in GENRES}
