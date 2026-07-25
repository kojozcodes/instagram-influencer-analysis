"""Audience estimation from an account's own public signals (spec F5 / 8 / 9).

IMPORTANT: this does not read individual followers. Instagram exposes real
follower demographics only for accounts connected to our app
(`follower_demographics`); for third-party accounts read via `business_discovery`
the field does not exist at all. Everything here is therefore an ESTIMATE, and
is labelled as such throughout the UI and the Excel.

Model
-----
Gender is NOT a count of "female words" in the account's text — that measures
who the content is *about*, which for a curation account is close to the
opposite of who follows it. Instead:

    logit(P(female audience)) = logit(topic base rate) + archetype shift

where the topic base rate comes from TOPIC_AUDIENCE and the archetype shift
accounts for showcase accounts (reposting photos of women pulls a male
audience). Age combines a population prior with any explicit age keywords.

Calibration status
------------------
The archetype shift is fitted to the only two ground-truth points available:
Instagram Insights exports the client supplied for yoga_bijo (59.1% F) and
surf_bijo (14.9% F). Two points cannot validate a model — they can only correct
a sign error and a centre-of-mass error, which is what they are used for here.
Treat the output as a direction plus a rough magnitude, never as a measurement.
`tests/test_demographics_calibration.py` pins both points as a regression guard.
"""
from __future__ import annotations

import math
import re

from ..models import AGE_BUCKETS, AccountData, DemographicsResult
from .keywords import (
    AGE_KEYWORDS,
    FEMALE_KEYWORDS,
    FEMALE_SUBJECT_MARKERS,
    MALE_KEYWORDS,
    MALE_SUBJECT_MARKERS,
    SHOWCASE_MARKERS,
    TOPIC_AUDIENCE,
)

_HASHTAG_RE = re.compile(r"#([^\s#、。,.!！?？]+)")

# Log-odds shift applied when an account curates photos OF one gender: the
# audience skews toward the other. Fitted to the two Insights exports above
# (yoga 0.78 -> 60.3% vs 59.1% actual; surf 0.32 -> 16.7% vs 14.9% actual).
SHOWCASE_SHIFT = 0.85

# Fallback when no topic matches: how strongly a personal creator's own gender
# pulls their audience, and the Laplace smoothing on that count.
PERSONAL_PULL = 0.55
GENDER_SMOOTHING = 2.5

# Population prior for age, as pseudo-counts. Japanese lifestyle accounts with a
# long posting history skew markedly older than the old model assumed (it put
# ~57% in 25-34; both ground-truth accounts are ~85% aged 35+).
AGE_PRIOR: dict[str, float] = {
    "13-17": 1.0, "18-24": 6.0, "25-34": 22.0, "35-44": 28.0,
    "45-54": 25.0, "55-64": 14.0, "65+": 4.0,
}
# Weight of that prior in pseudo-counts. Low enough that a dozen explicit age
# keywords can move the distribution, high enough that one stray word cannot.
AGE_PRIOR_STRENGTH = 0.08
AGE_NEIGHBOR_WEIGHT = 0.35


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _logit(p: float) -> float:
    p = min(max(p, 0.001), 0.999)
    return math.log(p / (1.0 - p))


def _find_age(text: str) -> str | None:
    for bucket, kws in AGE_KEYWORDS.items():
        if any(k in text for k in kws):
            return bucket
    return None


def _collect_signals(account: AccountData) -> list[str]:
    """Build the list of textual signals (analysis targets) for the account."""
    signals: list[str] = []
    corpus = " ".join(
        [account.biography or "", account.display_name or ""]
        + [p.caption or "" for p in account.posts]
    )
    signals.extend(m.group(1).lower() for m in _HASHTAG_RE.finditer(corpus))
    if account.biography:
        signals.append(account.biography.lower())
    if account.display_name:
        signals.append(account.display_name.lower())
    for p in account.posts:
        if p.caption:
            signals.append(p.caption.lower())
    return signals


def _profile_text(account: AccountData) -> str:
    """Bio + display name + username. The archetype is declared here, not in
    individual captions, so topic/archetype are resolved from the profile."""
    return " ".join([
        account.biography or "", account.display_name or "", account.username or "",
    ]).lower()


def _resolve_topic(text: str) -> tuple[str, float] | None:
    for name, kws, share in TOPIC_AUDIENCE:
        if any(k in text for k in kws):
            return name, share
    return None


def _detect_archetype(text: str, corpus: str) -> str | None:
    """'showcase_female' / 'showcase_male' / 'personal' / None."""
    is_showcase = any(k in text for k in SHOWCASE_MARKERS) or any(
        k in corpus for k in ("リポスト", "repost")
    )
    female_subject = any(k in text for k in FEMALE_SUBJECT_MARKERS)
    male_subject = any(k in text for k in MALE_SUBJECT_MARKERS)
    if is_showcase and female_subject and not male_subject:
        return "showcase_female"
    if is_showcase and male_subject and not female_subject:
        return "showcase_male"
    if is_showcase:
        return None
    return "personal"


def _personal_gender_base(signals: list[str]) -> tuple[float, int]:
    """Audience female-share for a creator posting their own content, plus the
    number of gender signals found."""
    female = sum(1 for s in signals if any(k in s for k in FEMALE_KEYWORDS))
    male = sum(1 for s in signals if any(k in s for k in MALE_KEYWORDS))
    if female + male == 0:
        return 0.5, 0
    f = female + GENDER_SMOOTHING
    m = male + GENDER_SMOOTHING
    creator_female = f / (f + m)
    # audience aligns with, but is less extreme than, the creator
    return 0.5 + (creator_female - 0.5) * 2 * PERSONAL_PULL, female + male


def demographics_from_counts(counts: dict[tuple[str, str], int]) -> DemographicsResult:
    """Build a result from Instagram's OWN follower_demographics counts.

    `counts` is keyed by (age band, gender) where gender is F/M/U. Instagram's
    own app reports the gender split over F+M only, so 'U' (undeclared) is
    excluded here too — otherwise our percentages would not line up with what
    the client sees in Insights.
    """
    grid: dict[str, float | None] = {}
    per_gender = {"female": "F", "male": "M"}
    total = sum(v for (_, g), v in counts.items() if g in ("F", "M"))
    if total <= 0:
        return DemographicsResult(source="measured", confidence="実測")

    for key, code in per_gender.items():
        for b in AGE_BUCKETS:
            grid[f"{key}_{b}"] = round(counts.get((b, code), 0) / total * 100, 1)

    female = sum(v for (_, g), v in counts.items() if g == "F")
    female_ratio = round(female / total * 100, 1)
    age_ratio = {
        b: round(
            sum(counts.get((b, c), 0) for c in ("F", "M")) / total * 100, 1
        )
        for b in AGE_BUCKETS
    }
    return DemographicsResult(
        male_ratio=round(100 - female_ratio, 1),
        female_ratio=female_ratio,
        grid=grid,
        age_ratio=age_ratio,
        age_measured_from_text=True,  # official figures, not a generic assumption
        analysis_target_count=total,
        classifiable_count=total,
        unknown_count=sum(v for (_, g), v in counts.items() if g == "U"),
        source="measured",
        confidence="実測",
        basis="Instagram公式インサイトの実測値",
    )


def estimate_demographics(account: AccountData, max_targets: int = 1000) -> DemographicsResult:
    signals = _collect_signals(account)[:max_targets]
    profile = _profile_text(account)
    corpus = " ".join(signals)

    # --- gender -----------------------------------------------------------
    topic = _resolve_topic(profile) or _resolve_topic(corpus)
    archetype = _detect_archetype(profile, corpus)

    basis_parts: list[str] = []
    if topic is not None:
        topic_name, base = topic
        basis_parts.append(f"ジャンル: {topic_name}")
        gender_signal_count = len(signals)
    else:
        base, gender_signal_count = _personal_gender_base(signals)
        if gender_signal_count:
            basis_parts.append("発信者の属性から推定")

    logit = _logit(base)
    if archetype == "showcase_female":
        logit -= SHOWCASE_SHIFT
        basis_parts.append("女性を紹介するまとめ型（男性寄りに補正）")
    elif archetype == "showcase_male":
        logit += SHOWCASE_SHIFT
        basis_parts.append("男性を紹介するまとめ型（女性寄りに補正）")
    elif archetype == "personal" and topic is not None:
        basis_parts.append("本人発信型")

    if topic is None and gender_signal_count == 0:
        female_ratio = male_ratio = None
    else:
        female_ratio = round(_sigmoid(logit) * 100, 1)
        male_ratio = round(100 - female_ratio, 1)

    # --- age --------------------------------------------------------------
    age_weight = {b: AGE_PRIOR[b] * AGE_PRIOR_STRENGTH for b in AGE_BUCKETS}
    age_signal_count = 0
    for sig in signals:
        bucket = _find_age(sig)
        if bucket is None:
            continue
        age_signal_count += 1
        i = AGE_BUCKETS.index(bucket)
        age_weight[bucket] += 1.0
        if i - 1 >= 0:
            age_weight[AGE_BUCKETS[i - 1]] += AGE_NEIGHBOR_WEIGHT
        if i + 1 < len(AGE_BUCKETS):
            age_weight[AGE_BUCKETS[i + 1]] += AGE_NEIGHBOR_WEIGHT

    total = sum(age_weight.values())
    age_ratio = {b: round(age_weight[b] / total * 100, 1) for b in AGE_BUCKETS}

    # --- joint grid (independence assumption) ------------------------------
    grid: dict[str, float | None] = {}
    for key, gratio in (("male", male_ratio), ("female", female_ratio)):
        for b in AGE_BUCKETS:
            grid[f"{key}_{b}"] = (
                None if gratio is None else round(gratio * age_ratio[b] / 100, 1)
            )

    classifiable = sum(
        1 for s in signals
        if _find_age(s) or any(k in s for k in FEMALE_KEYWORDS + MALE_KEYWORDS)
    )

    # --- confidence --------------------------------------------------------
    if topic is not None and archetype is not None and len(signals) >= 20:
        confidence = "高"
    elif topic is not None and len(signals) >= 5:
        confidence = "中"
    else:
        confidence = "低"
    if age_signal_count == 0:
        basis_parts.append(
            "年代：このアカウント固有の年齢情報は検出されず、全体傾向値を表示"
        )

    return DemographicsResult(
        male_ratio=male_ratio,
        female_ratio=female_ratio,
        grid=grid,
        age_ratio=age_ratio,
        age_measured_from_text=age_signal_count > 0,
        analysis_target_count=len(signals),
        classifiable_count=classifiable,
        unknown_count=len(signals) - classifiable,
        source="estimated",
        confidence=confidence,
        basis=" / ".join(basis_parts),
    )
