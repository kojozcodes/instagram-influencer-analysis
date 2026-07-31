"""Audience estimation from an account's own public signals (spec F5 / 8 / 9).

IMPORTANT: this never reads individual followers. Instagram exposes real
follower demographics only for accounts connected to our app
(`follower_demographics`); for third-party accounts read via `business_discovery`
the field does not exist. Everything here is an ESTIMATE and is labelled as such
in the UI and the Excel.

Implements the change list approved by 株式会社ビューズ on 2026-07-30
(改善内容一覧_ASIS-TOBE.xlsx, sheet 4):

  1. age baseline split into four genre-linked patterns
  2. age-expression reading fixed (all expressions / ranges / boilerplate)
  3. per-account scoring axes added
  4. genre decided by most keyword hits, not first hit
  5. genres 13 -> 24                          (see keywords.py)
  6. personal accounts blended toward the creator's own gender
  7. vocabulary expanded                      (see keywords.py)

Deliberately NOT implemented: the account-ID-derived ±0.1-2.9% fluctuation
proposed in the client's materials. It would make two accounts differ because
their names differ, which cannot be explained to an end client.

Gender model
------------
    logit(P(female)) = genre base
                       + creator identity  (bio + display-name wording)
                       + given-name characters
                       + hashtags
                       + media format
                       + showcase inversion

For a personal account with a clear creator signal, the genre base is BLENDED
toward the creator's own gender rather than merely nudged (item 6) — a female
fitness trainer's audience is female, even though the fitness genre as a whole
skews male.

Calibration status
------------------
Weights are the ranges given in the client's own materials. They are NOT fitted
to the 19 verification accounts, because those same accounts were used to design
the model; fitting and then reporting on them would prove nothing. The client
runs a fresh 10-account verification after each change, and that is the figure
that counts.
"""
from __future__ import annotations

import math
import re

from ..models import AGE_BUCKETS, AccountData, DemographicsResult
from .keywords import (
    AGE_KEYWORDS,
    AGE_PATTERNS,
    DEFAULT_AGE_PATTERN,
    FEMALE_KEYWORDS,
    FEMALE_SUBJECT_MARKERS,
    GENRE_AGE_PATTERN,
    MALE_FIRST_MARKERS,
    MALE_KEYWORDS,
    MALE_SUBJECT_MARKERS,
    NAME_FEMALE_CHARS,
    NAME_MALE_CHARS,
    SHOWCASE_MARKERS,
    TOPIC_AUDIENCE,
)

_HASHTAG_RE = re.compile(r"#([^\s#、。,.!！?？]+)")
# "10代から70代" / "20代〜40代" / "10代-60代" — a span, not a single band.
_AGE_RANGE_RE = re.compile(r"(\d{1,2})\s*代\s*(?:から|〜|~|ー|-|–|to)\s*(\d{1,2})\s*代")

# --- axis strengths, in log-odds ------------------------------------------
# Profile text and display name are largely the same words, so they form ONE
# axis; scoring them separately triple-counted a single signal.
W_CREATOR = 0.90
W_NAME_CHARS = 0.55
W_HASHTAG = 0.35
W_MEDIA = 0.15
SHOWCASE_SHIFT = 0.85
SMOOTH = 2.0          # one stray word must not swing an axis to its maximum

# item 6: blending for personal accounts
BLEND_CLEAR = 0.25    # creator signal must be at least this strong to blend
BLEND_MAX = 0.60      # creator never fully overrides the genre
CREATOR_IMPLIED_MAX = 0.80   # a wholly female creator implies ~90% female

# item 1: how strongly the genre age pattern holds against explicit age words
AGE_PATTERN_STRENGTH = 0.12
AGE_NEIGHBOR_WEIGHT = 0.35


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _logit(p: float) -> float:
    p = min(max(p, 0.001), 0.999)
    return math.log(p / (1.0 - p))


def _signed_score(text: str) -> float:
    """Smoothed signed proportion in [-1, 1]; +1 means purely female wording."""
    t = (text or "").lower()
    f = sum(1 for k in FEMALE_KEYWORDS if k in t)
    m = sum(1 for k in MALE_KEYWORDS if k in t)
    if any(k in t for k in MALE_FIRST_MARKERS):
        # 育児/子育て also appear in fathers' profiles
        f = max(0, f - 2)
    if f == 0 and m == 0:
        return 0.0
    return (f - m) / (f + m + SMOOTH)


def _name_char_score(display_name: str) -> float:
    """Signed score from Japanese given-name characters, in [-1, 1]."""
    t = display_name or ""
    f = sum(1 for c in NAME_FEMALE_CHARS if c in t)
    m = sum(1 for c in NAME_MALE_CHARS if c in t)
    if f == 0 and m == 0:
        return 0.0
    return (f - m) / (f + m + 1.0)


def _resolve_genre(text: str) -> tuple[str | None, float | None]:
    """Approved item 4: the genre with the MOST keyword hits wins.

    Taking the first hit meant a frugal-living mama account matched
    ビジネス・副業・マネー (40% female) on the single word 節約.
    """
    t = (text or "").lower()
    best_name, best_share, best_hits = None, None, 0
    for name, kws, share in TOPIC_AUDIENCE:
        hits = sum(1 for k in kws if k in t)
        if hits > best_hits:          # ties keep the earlier (more specific) genre
            best_name, best_share, best_hits = name, share, hits
    return best_name, best_share


def _unique_lines(account: AccountData) -> list[str]:
    """Distinct text lines across bio, display name and captions.

    Approved item 2: a signature block repeated in every caption previously
    counted once per post. One hairdresser's 「10代から70代のお客様を担当」
    appeared in 23 of 30 captions and drove 52% of his followers into 13-17.
    """
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
    """Every age band a single line points to (approved item 2).

    Previously only the first matching band was taken, so 「10代から70代」 was
    read as 13-17 alone. A range now credits every band it spans, which for a
    wide span is close to neutral — the correct reading of "all ages".
    """
    bands: list[str] = []

    for lo, hi in _AGE_RANGE_RE.findall(line):
        lo_i, hi_i = int(lo), int(hi)
        if lo_i > hi_i:
            lo_i, hi_i = hi_i, lo_i
        for b, (b_lo, b_hi) in _BAND_DECADES.items():
            if b_lo <= hi_i and b_hi >= lo_i:
                bands.append(b)

    if bands:
        return bands       # an explicit range supersedes single-word matches

    for bucket, kws in AGE_KEYWORDS.items():
        if any(k in line for k in kws):
            bands.append(bucket)
    return bands


# decade span covered by each band, for range matching
_BAND_DECADES: dict[str, tuple[int, int]] = {
    "13-17": (10, 10), "18-24": (10, 20), "25-34": (20, 30), "35-44": (30, 40),
    "45-54": (40, 50), "55-64": (50, 60), "65+": (60, 90),
}


def demographics_from_counts(counts: dict[tuple[str, str], int]) -> DemographicsResult:
    """Build a result from Instagram's OWN follower_demographics counts.

    `counts` is keyed by (age band, gender) with gender F/M/U. Instagram's own
    UI reports the split over F+M only, so 'U' is excluded here too.
    """
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
        male_ratio=round(100 - female_ratio, 1),
        female_ratio=female_ratio,
        grid=grid,
        age_ratio=age_ratio,
        age_measured_from_text=True,
        analysis_target_count=total,
        classifiable_count=total,
        unknown_count=sum(v for (_, g), v in counts.items() if g == "U"),
        source="measured",
        confidence="実測",
        basis="Instagram公式インサイトの実測値",
    )


def estimate_demographics(account: AccountData, max_targets: int = 1000) -> DemographicsResult:
    lines = _unique_lines(account)[:max_targets]
    bio = account.biography or ""
    display = account.display_name or ""
    profile_text = f"{bio} {display} {account.username or ''}".lower()
    corpus = " ".join(lines)

    # --- genre (items 4, 5) -------------------------------------------------
    genre, base = _resolve_genre(profile_text)
    if base is None:
        genre, base = _resolve_genre(corpus)
    if base is None:
        genre, base = "（該当ジャンルなし）", 0.50

    basis: list[str] = [f"ジャンル: {genre}({base * 100:.0f}%)"]

    # --- archetype ----------------------------------------------------------
    is_showcase = any(k in profile_text for k in SHOWCASE_MARKERS) or any(
        k in corpus for k in ("リポスト", "repost")
    )
    female_subject = any(k in profile_text for k in FEMALE_SUBJECT_MARKERS)
    male_subject = any(k in profile_text for k in MALE_SUBJECT_MARKERS)

    # --- gender axes (items 3, 6) ------------------------------------------
    text_score = _signed_score(f"{bio} {display}")
    name_score = _name_char_score(display)
    creator = max(-1.0, min(1.0, text_score + 0.6 * name_score))

    x = _logit(base)

    # The creator axes apply to 本人発信型 only (item 6). On a showcase account
    # the female wording describes the SUBJECT of the photos, not the creator —
    # counting it here would re-introduce the very error the showcase inversion
    # exists to correct (yoga_bijo: 60.2% -> 72.3% against 59.1% actual).
    if not is_showcase:
        if abs(creator) >= BLEND_CLEAR:
            # item 6 — blend, do not merely nudge
            w = min(BLEND_MAX, abs(creator))
            implied = 0.5 + 0.5 * creator * CREATOR_IMPLIED_MAX
            blended = (1 - w) * x + w * _logit(implied)
            # A female creator may only raise the female estimate, never lower
            # it: in a genre that is already 93% female the base already
            # accounts for her, and blending toward the weaker implied value
            # would drag a nail account down from 93% to 86%.
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

    tag_score = _signed_score(" ".join(_HASHTAG_RE.findall(corpus)))
    if abs(tag_score) > 0.05:
        x += tag_score * W_HASHTAG
        basis.append(f"ハッシュタグ: {tag_score * W_HASHTAG:+.2f}")

    if account.posts:
        reels = sum(1 for p in account.posts
                    if (p.media_product_type or "").upper() == "REELS")
        if reels / len(account.posts) >= 0.8:
            x += W_MEDIA
            basis.append(f"リール中心: {W_MEDIA:+.2f}")

    if is_showcase and female_subject and not male_subject:
        x -= SHOWCASE_SHIFT
        basis.append(f"まとめ型(女性紹介): {-SHOWCASE_SHIFT:+.2f}")
    elif is_showcase and male_subject and not female_subject:
        x += SHOWCASE_SHIFT
        basis.append(f"まとめ型(男性紹介): {SHOWCASE_SHIFT:+.2f}")

    # No genre, no wording, no name signal, no tags -> we know nothing. Report
    # unknown rather than a confident-looking 50/50, which would print in the
    # Excel as though it were an estimate.
    has_signal = (
        genre != "（該当ジャンルなし）"
        or abs(creator) > 0
        or abs(name_score) > 0
        or abs(tag_score) > 0
        or is_showcase
    )
    if has_signal:
        female_ratio: float | None = round(_sigmoid(x) * 100, 1)
        male_ratio: float | None = round(100 - female_ratio, 1)
    else:
        female_ratio = male_ratio = None
        basis = ["性別を判定できる公開情報がありません"]

    # --- age (items 1, 2) ---------------------------------------------------
    pattern_name = GENRE_AGE_PATTERN.get(genre, DEFAULT_AGE_PATTERN)
    pattern = AGE_PATTERNS[pattern_name]
    age_weight = {b: pattern[b] * AGE_PATTERN_STRENGTH for b in AGE_BUCKETS}

    age_signals = 0
    for line in lines:
        bands = _age_hits(line)
        if not bands:
            continue
        age_signals += 1
        share = 1.0 / len(bands)      # a range spreads, a single word concentrates
        for b in bands:
            i = AGE_BUCKETS.index(b)
            age_weight[b] += share
            if len(bands) == 1:       # neighbour bleed only for a definite band
                if i - 1 >= 0:
                    age_weight[AGE_BUCKETS[i - 1]] += AGE_NEIGHBOR_WEIGHT
                if i + 1 < len(AGE_BUCKETS):
                    age_weight[AGE_BUCKETS[i + 1]] += AGE_NEIGHBOR_WEIGHT

    total_w = sum(age_weight.values())
    age_ratio = {b: round(age_weight[b] / total_w * 100, 1) for b in AGE_BUCKETS}
    basis.append(f"年代基準: {pattern_name}"
                 + ("" if age_signals else "（年齢表現なし）"))

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
        male_ratio=male_ratio,
        female_ratio=female_ratio,
        grid=grid,
        age_ratio=age_ratio,
        age_measured_from_text=age_signals > 0,
        analysis_target_count=len(lines),
        classifiable_count=classifiable,
        unknown_count=len(lines) - classifiable,
        source="estimated",
        confidence=confidence,
        basis=" / ".join(basis),
    )
