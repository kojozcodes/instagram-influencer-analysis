"""Audience estimation from an account's own public signals (spec F5 / 8 / 9).

IMPORTANT: this never reads individual followers. Instagram exposes real
follower demographics only for accounts connected to our app; for third-party
accounts read via `business_discovery` the field does not exist. Everything here
is an ESTIMATE and is labelled as such in the UI and the Excel.

Implements the batch approved by 株式会社ビューズ on 2026-08-03:

  1. 28-genre structure with weighted scoring (strong 3.0 / medium 2.0 / weak 1.0)
  2. AND-conditions (節約 scores only alongside a qualifying partner word)
  3. まとめ型 threshold — profile/name unconditional, captions only at >= 20%
  4. mama / lifestyle +5% cap
  5. negative keywords
  6. メンズ override, profile text and display name ONLY (never hashtags)
  7. reverse-pattern detection from text/hashtags (exposure / performer framing)

Deliberately NOT in this batch, by the client's instruction: Gemini/Vertex AI
image analysis, and the account-ID-derived jitter.

Gender model
------------
    logit(P(female)) = genre base
                       + creator identity      (personal accounts only)
                       + given-name characters (personal accounts only)
                       + hashtags
                       + media format
                       + showcase inversion
                       + reverse-pattern (exposure) shift
                       -> メンズ override, then the mama/lifestyle cap

Calibration status
------------------
Genre ratios are our own measured values, kept in preference to the proposed
reductions on the client's instruction — testing showed 3 of 4 accounts got
worse under those. Axis weights come from the client's stated ranges and are NOT
fitted to the verification accounts, since those accounts shaped the design.
"""
from __future__ import annotations

import math
import re

from ..models import AGE_BUCKETS, AccountData, DemographicsResult
from .keywords import (
    AGE_KEYWORDS,
    AGE_PATTERNS,
    AND_ONLY_WORDS,
    AND_RULES,
    DEFAULT_AGE_PATTERN,
    EXPOSURE_SHIFT_STRONG,
    EXPOSURE_SHIFT_WEAK,
    EXPOSURE_TAGS,
    FEMALE_KEYWORDS,
    FEMALE_SUBJECT_MARKERS,
    GENRES,
    MALE_FIRST_MARKERS,
    MALE_KEYWORDS,
    MALE_SUBJECT_MARKERS,
    MENS_FLOOR,
    MENS_MARKERS,
    MENS_OVERRIDE_SHIFT,
    NAME_FEMALE_CHARS,
    NAME_MALE_CHARS,
    NEGATIVE_KEYWORDS,
    NEUTRAL_COMPOUNDS,
    PERFORMER_MARKERS,
    SHOWCASE_CAPTION_THRESHOLD,
    SHOWCASE_MARKERS,
)

_HASHTAG_RE = re.compile(r"#([^\s#、。,.!！?？]+)")
_AGE_RANGE_RE = re.compile(r"(\d{1,2})\s*代\s*(?:から|〜|~|ー|-|–|to)\s*(\d{1,2})\s*代")

WEIGHTS = {"s": 3.0, "m": 2.0, "w": 1.0}

W_CREATOR = 0.90
W_NAME_CHARS = 0.55
W_HASHTAG = 0.35
W_MEDIA = 0.15
SHOWCASE_SHIFT = 0.85
SMOOTH = 2.0

BLEND_CLEAR = 0.25
BLEND_MAX = 0.60
CREATOR_IMPLIED_MAX = 0.80

# genres where the female-keyword bonus is capped (approved item: +5% max)
CAPPED_GENRES = {"育児・ワンオペ・プレママ", "暮らし・インテリア",
                 "子育て・キッズ（小〜中学生）"}
CAP_MARGIN_PT = 5.0

AGE_PATTERN_STRENGTH = 0.08
AGE_NEIGHBOR_WEIGHT = 0.35

_BAND_DECADES: dict[str, tuple[int, int]] = {
    "13-17": (10, 10), "18-24": (10, 20), "25-34": (20, 30), "35-44": (30, 40),
    "45-54": (40, 50), "55-64": (50, 60), "65+": (60, 90),
}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _logit(p: float) -> float:
    p = min(max(p, 0.001), 0.999)
    return math.log(p / (1.0 - p))


def _strip_neutral(text: str) -> str:
    """Blank out compounds that contain a gendered substring but are neutral —
    夫婦 contains 夫, which once read a mother as male."""
    for w in NEUTRAL_COMPOUNDS:
        text = text.replace(w, "　")
    return text


def _signed_score(text: str) -> float:
    """Smoothed signed proportion in [-1, 1]; +1 means purely female wording."""
    t = _strip_neutral((text or "").lower())
    f = sum(1 for k in FEMALE_KEYWORDS if k in t)
    m = sum(1 for k in MALE_KEYWORDS if k in t)
    if any(k in t for k in MALE_FIRST_MARKERS):
        f = max(0, f - 2)          # 育児/子育て appear in fathers' profiles too
    if f == 0 and m == 0:
        return 0.0
    return (f - m) / (f + m + SMOOTH)


def _name_char_score(display_name: str) -> float:
    t = display_name or ""
    f = sum(1 for c in NAME_FEMALE_CHARS if c in t)
    m = sum(1 for c in NAME_MALE_CHARS if c in t)
    if f == 0 and m == 0:
        return 0.0
    return (f - m) / (f + m + 1.0)


def _genre_scores(text: str) -> dict[str, float]:
    """Weighted score per genre: 3.0/2.0/1.0 by vocabulary strength."""
    t = (text or "").lower()
    scores: dict[str, float] = {}
    for name, _ratio, kw, _pat in GENRES:
        s = 0.0
        for tier, weight in WEIGHTS.items():
            for word in kw[tier]:
                if word in AND_ONLY_WORDS:
                    continue           # scored only via AND_RULES
                if word in t:
                    s += weight
        if s:
            scores[name] = s

    # AND-conditions: an ambiguous trigger scores only with a partner present
    for trigger, partners, genre, weight in AND_RULES:
        if trigger in t and any(p in t for p in partners):
            scores[genre] = scores.get(genre, 0.0) + weight

    # negative keywords suppress a genre outright
    for genre, negatives in NEGATIVE_KEYWORDS.items():
        if genre in scores and any(n in t for n in negatives):
            del scores[genre]
    return scores


def _resolve_genre(text: str) -> tuple[str | None, float | None, str]:
    scores = _genre_scores(text)
    if not scores:
        return None, None, DEFAULT_AGE_PATTERN
    best = max(scores.values())
    for name, ratio, _kw, pat in GENRES:      # ties keep the earlier entry
        if scores.get(name) == best:
            return name, ratio, pat
    return None, None, DEFAULT_AGE_PATTERN


def _unique_lines(account: AccountData) -> list[str]:
    """Distinct text lines. A signature block repeated in every caption must
    count once — one hairdresser's 「10代から70代のお客様」 appeared in 23 of 30
    captions and pushed 52% of his followers into 13-17."""
    seen: set[str] = set()
    out: list[str] = []
    raw = [account.biography or "", account.display_name or ""]
    raw += [p.caption or "" for p in account.posts]
    for block in raw:
        for line in re.split(r"[\n\r]+", block):
            norm = re.sub(r"\s+", "", line).lower()
            if norm and norm not in seen:
                seen.add(norm)
                out.append(line.lower())
    return out


def _age_hits(line: str) -> list[str]:
    """Every age band a line points to. A range credits all bands it spans,
    so 「10代から70代」 reads as 'all ages' rather than 'teenagers'."""
    bands: list[str] = []
    for lo, hi in _AGE_RANGE_RE.findall(line):
        lo_i, hi_i = int(lo), int(hi)
        if lo_i > hi_i:
            lo_i, hi_i = hi_i, lo_i
        for b, (b_lo, b_hi) in _BAND_DECADES.items():
            if b_lo <= hi_i and b_hi >= lo_i:
                bands.append(b)
    if bands:
        return bands
    for bucket, kws in AGE_KEYWORDS.items():
        if any(k in line for k in kws):
            bands.append(bucket)
    return bands


def _is_showcase(profile: str, captions: list[str]) -> bool:
    """Profile/name markers are unconditional. In captions the same words appear
    on ordinary personal posts, so they count only at >= 20% of recent posts."""
    if any(k in profile for k in SHOWCASE_MARKERS):
        return True
    if not captions:
        return False
    hits = sum(1 for c in captions if any(k in c for k in SHOWCASE_MARKERS))
    return hits / len(captions) >= SHOWCASE_CAPTION_THRESHOLD


def demographics_from_counts(counts: dict[tuple[str, str], int]) -> DemographicsResult:
    """Build a result from Instagram's OWN follower_demographics counts.
    Gender is normalised over F+M only, as Instagram's own UI does."""
    grid: dict[str, float | None] = {}
    total = sum(v for (_, g), v in counts.items() if g in ("F", "M"))
    if total <= 0:
        return DemographicsResult(source="measured", confidence="実測")
    for key, code in (("female", "F"), ("male", "M")):
        for b in AGE_BUCKETS:
            grid[f"{key}_{b}"] = round(counts.get((b, code), 0) / total * 100, 1)
    female = sum(v for (_, g), v in counts.items() if g == "F")
    female_ratio = round(female / total * 100, 1)
    age_ratio = {
        b: round(sum(v for (a, g), v in counts.items() if a == b and g in ("F", "M"))
                 / total * 100, 1)
        for b in AGE_BUCKETS
    }
    return DemographicsResult(
        male_ratio=round(100 - female_ratio, 1), female_ratio=female_ratio,
        grid=grid, age_ratio=age_ratio, age_measured_from_text=True,
        analysis_target_count=total, classifiable_count=total,
        unknown_count=sum(v for (_, g), v in counts.items() if g == "U"),
        source="measured", confidence="実測",
        basis="Instagram公式インサイトの実測値",
    )


def estimate_demographics(account: AccountData, max_targets: int = 1000) -> DemographicsResult:
    lines = _unique_lines(account)[:max_targets]
    bio = account.biography or ""
    display = account.display_name or ""
    profile_text = f"{bio} {display} {account.username or ''}".lower()
    captions = [(p.caption or "").lower() for p in account.posts if p.caption]
    corpus = " ".join(lines)
    tags = " ".join(_HASHTAG_RE.findall(corpus)).lower()

    # --- genre (weighted, AND-conditions, negative keywords) ---------------
    genre, base, pattern_name = _resolve_genre(profile_text)
    if base is None:
        genre, base, pattern_name = _resolve_genre(corpus)
    if base is None:
        genre, base, pattern_name = "（該当ジャンルなし）", 0.50, DEFAULT_AGE_PATTERN

    # --- reverse pattern, applied as a GENRE decision ----------------------
    # Approved item 2. Explicit exposure / photo-subject vocabulary means the
    # account is sold on the creator's appearance, which draws a predominantly
    # male audience. Treating it as a genre (rather than nudging a beauty base)
    # is both more accurate and explainable: 世手子様 tags #SHEINbikini and is
    # 28.6% female, where a 88% beauty base could not reach.
    exposure = [k for k in EXPOSURE_TAGS if k in tags or k in profile_text]
    performer = [k for k in PERFORMER_MARKERS if k in profile_text]
    if exposure:
        genre, base, pattern_name = "グラビア・被写体", 0.20, "若年層型"

    basis: list[str] = [f"ジャンル: {genre}({base * 100:.0f}%)"]
    if exposure:
        basis.append(f"露出・被写体語: {'/'.join(exposure[:3])}")

    # --- archetype ---------------------------------------------------------
    showcase = _is_showcase(profile_text, captions)
    female_subject = any(k in profile_text for k in FEMALE_SUBJECT_MARKERS)
    male_subject = any(k in profile_text for k in MALE_SUBJECT_MARKERS)

    text_score = _signed_score(f"{bio} {display}")
    name_score = _name_char_score(display)
    creator = max(-1.0, min(1.0, text_score + 0.6 * name_score))
    tag_score = _signed_score(tags)

    x = _logit(base)

    # Creator axes apply to 本人発信型 only: on a showcase account the female
    # wording describes the SUBJECT of the photos, not the creator.
    if not showcase:
        if abs(creator) >= BLEND_CLEAR:
            w = min(BLEND_MAX, abs(creator))
            implied = 0.5 + 0.5 * creator * CREATOR_IMPLIED_MAX
            blended = (1 - w) * x + w * _logit(implied)
            # a female creator may only raise the female estimate, never lower it
            x = max(x, blended) if creator > 0 else min(x, blended)
            if abs(x - _logit(base)) > 0.01:
                basis.append(f"本人発信型: 発信者属性を混合(重み{w:.2f})")
        else:
            x += creator * W_CREATOR
            if abs(creator) > 0.05:
                basis.append(f"プロフィール/名前: {creator * W_CREATOR:+.2f}")
        if abs(name_score) > 0.05:
            x += name_score * W_NAME_CHARS
            basis.append(f"アカウント名: {name_score * W_NAME_CHARS:+.2f}")

    if abs(tag_score) > 0.05:
        x += tag_score * W_HASHTAG
        basis.append(f"ハッシュタグ: {tag_score * W_HASHTAG:+.2f}")

    if account.posts:
        reels = sum(1 for p in account.posts
                    if (p.media_product_type or "").upper() == "REELS")
        if reels / len(account.posts) >= 0.8:
            x += W_MEDIA
            basis.append(f"リール中心: {W_MEDIA:+.2f}")

    if showcase and female_subject and not male_subject:
        x -= SHOWCASE_SHIFT
        basis.append(f"まとめ型(女性紹介): {-SHOWCASE_SHIFT:+.2f}")
    elif showcase and male_subject and not female_subject:
        x += SHOWCASE_SHIFT
        basis.append(f"まとめ型(男性紹介): {SHOWCASE_SHIFT:+.2f}")

    # Performer framing without explicit exposure wording is a weaker signal,
    # so it stays a shift rather than a genre decision.
    if performer and not exposure and x > 0:
        x += EXPOSURE_SHIFT_WEAK
        basis.append(f"モデル・タレント傾向: {EXPOSURE_SHIFT_WEAK:+.2f}")

    # --- メンズ override: profile text and display name ONLY ---------------
    mens_scope = f"{bio} {display}".lower()
    if any(k in mens_scope for k in MENS_MARKERS):
        x = min(x, _logit(base) + MENS_OVERRIDE_SHIFT)
        x = max(x, _logit(MENS_FLOOR))
        basis.append("メンズ指定: 男性寄りに補正")

    female_ratio: float | None = round(_sigmoid(x) * 100, 1)

    # --- mama / lifestyle cap ---------------------------------------------
    if genre in CAPPED_GENRES and female_ratio is not None:
        ceiling = base * 100 + CAP_MARGIN_PT
        if female_ratio > ceiling:
            female_ratio = round(ceiling, 1)
            basis.append(f"加点上限: {ceiling:.0f}%")

    has_signal = (
        genre != "（該当ジャンルなし）"
        or abs(creator) > 0 or abs(name_score) > 0 or abs(tag_score) > 0 or showcase
    )
    if not has_signal:
        female_ratio = None
        basis = ["性別を判定できる公開情報がありません"]
    male_ratio = None if female_ratio is None else round(100 - female_ratio, 1)

    # --- age ---------------------------------------------------------------
    pattern = AGE_PATTERNS[pattern_name]
    age_weight = {b: pattern[b] * AGE_PATTERN_STRENGTH for b in AGE_BUCKETS}
    age_signals = 0
    for line in lines:
        bands = _age_hits(line)
        if not bands:
            continue
        age_signals += 1
        share = 1.0 / len(bands)
        for b in bands:
            i = AGE_BUCKETS.index(b)
            age_weight[b] += share
            if len(bands) == 1:
                if i - 1 >= 0:
                    age_weight[AGE_BUCKETS[i - 1]] += AGE_NEIGHBOR_WEIGHT
                if i + 1 < len(AGE_BUCKETS):
                    age_weight[AGE_BUCKETS[i + 1]] += AGE_NEIGHBOR_WEIGHT

    total_w = sum(age_weight.values())
    age_ratio = {b: round(age_weight[b] / total_w * 100, 1) for b in AGE_BUCKETS}
    basis.append(f"年代基準: {pattern_name}" + ("" if age_signals else "（年齢表現なし）"))

    grid: dict[str, float | None] = {}
    for key, gratio in (("male", male_ratio), ("female", female_ratio)):
        for b in AGE_BUCKETS:
            grid[f"{key}_{b}"] = (
                None if gratio is None else round(gratio * age_ratio[b] / 100, 1)
            )

    classifiable = sum(
        1 for s in lines
        if _age_hits(s) or any(k in s for k in FEMALE_KEYWORDS + MALE_KEYWORDS)
    )
    if genre != "（該当ジャンルなし）" and len(lines) >= 20:
        confidence = "高"
    elif genre != "（該当ジャンルなし）":
        confidence = "中"
    else:
        confidence = "低"

    return DemographicsResult(
        male_ratio=male_ratio, female_ratio=female_ratio, grid=grid,
        age_ratio=age_ratio, age_measured_from_text=age_signals > 0,
        analysis_target_count=len(lines), classifiable_count=classifiable,
        unknown_count=len(lines) - classifiable,
        source="estimated", confidence=confidence, basis=" / ".join(basis),
    )
