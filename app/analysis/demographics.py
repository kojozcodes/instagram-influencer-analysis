"""Demographic estimation from an account's own public signals (spec F5 / 8 / 9).

IMPORTANT: This does not read individual followers' age or gender. It scores the
account's OWN public text (bio, display name, captions, hashtags) against keyword
dictionaries and produces an ESTIMATED audience distribution. Counts of analyzed
vs. classifiable vs. unknown signals are reported for transparency (spec 9).
"""
from __future__ import annotations

import re

from ..models import AGE_BUCKETS, AccountData, DemographicsResult
from .keywords import AGE_KEYWORDS, FEMALE_KEYWORDS, MALE_KEYWORDS

_HASHTAG_RE = re.compile(r"#([^\s#、。,.!！?？]+)")

# --- Estimation smoothing (keeps output realistic instead of all-or-nothing) ---
# Gender: additive (Laplace) smoothing. Each gender starts with this many
# "pseudo-signals", which pulls extreme ratios toward 50/50 when evidence is
# thin, and lets strong evidence still dominate. e.g. 15 female / 0 male ->
# ~85/15 (clearly female) rather than 100/0; 2 female / 0 male -> ~64/36 (weak).
GENDER_SMOOTHING = 2.5

# Age: each age signal also credits its adjacent bands (a 25-34 audience spills
# into 18-24 and 35-44), then every band gets a small pseudo-count. Together
# these spread the distribution across bands instead of putting 100% in one.
AGE_NEIGHBOR_WEIGHT = 0.35
AGE_SMOOTHING = 0.4


def _find_gender(text: str) -> str | None:
    """Return 'M', 'F', or None for a single signal's text."""
    f = any(k in text for k in FEMALE_KEYWORDS)
    m = any(k in text for k in MALE_KEYWORDS)
    if f and not m:
        return "F"
    if m and not f:
        return "M"
    return None  # ambiguous or none


def _find_age(text: str) -> str | None:
    for bucket, kws in AGE_KEYWORDS.items():
        if any(k in text for k in kws):
            return bucket
    return None


def _collect_signals(account: AccountData) -> list[str]:
    """Build the list of textual signals (analysis targets) for the account."""
    signals: list[str] = []

    # Hashtags from bio + captions are each an individual signal.
    corpus = " ".join(
        [account.biography or "", account.display_name or ""]
        + [p.caption or "" for p in account.posts]
    )
    signals.extend(m.group(1).lower() for m in _HASHTAG_RE.finditer(corpus))

    # Bio and display name each contribute one signal (the profile text itself).
    if account.biography:
        signals.append(account.biography.lower())
    if account.display_name:
        signals.append(account.display_name.lower())
    # Each caption contributes one signal.
    for p in account.posts:
        if p.caption:
            signals.append(p.caption.lower())

    return signals


def estimate_demographics(account: AccountData, max_targets: int = 1000) -> DemographicsResult:
    signals = _collect_signals(account)[:max_targets]

    female = male = 0
    age_signal_count = 0
    # Neighbor-bled age weights (float): a signal in bucket i credits i and i±1.
    age_weight: dict[str, float] = {b: 0.0 for b in AGE_BUCKETS}
    classifiable = 0

    for sig in signals:
        gender = _find_gender(sig)
        age = _find_age(sig)
        if gender == "F":
            female += 1
        elif gender == "M":
            male += 1
        if age is not None:
            age_signal_count += 1
            i = AGE_BUCKETS.index(age)
            age_weight[AGE_BUCKETS[i]] += 1.0
            if i - 1 >= 0:
                age_weight[AGE_BUCKETS[i - 1]] += AGE_NEIGHBOR_WEIGHT
            if i + 1 < len(AGE_BUCKETS):
                age_weight[AGE_BUCKETS[i + 1]] += AGE_NEIGHBOR_WEIGHT
        if gender is not None or age is not None:
            classifiable += 1

    analysis_target_count = len(signals)
    unknown_count = analysis_target_count - classifiable

    # Gender ratios (percent). Laplace-smoothed so thin evidence isn't reported
    # as 0/100. Unknown (no gender signal at all) -> None.
    male_ratio: float | None = None
    female_ratio: float | None = None
    if female + male > 0:
        f = female + GENDER_SMOOTHING
        m = male + GENDER_SMOOTHING
        female_ratio = round(f / (f + m) * 100, 1)
        male_ratio = round(100 - female_ratio, 1)

    # Age distribution (percent). Neighbor-bled + Laplace-smoothed so it spreads
    # across bands. Unknown (no age signal at all) -> all None.
    age_ratio: dict[str, float | None] = {b: None for b in AGE_BUCKETS}
    if age_signal_count > 0:
        smoothed = {b: age_weight[b] + AGE_SMOOTHING for b in AGE_BUCKETS}
        total = sum(smoothed.values())
        for b in AGE_BUCKETS:
            age_ratio[b] = round(smoothed[b] / total * 100, 1)

    # Joint age x gender grid = age distribution x gender split.
    grid: dict[str, float | None] = {}
    for gender_key, gratio in (("male", male_ratio), ("female", female_ratio)):
        for b in AGE_BUCKETS:
            if gratio is None or age_ratio[b] is None:
                grid[f"{gender_key}_{b}"] = None
            else:
                grid[f"{gender_key}_{b}"] = round(gratio * age_ratio[b] / 100, 1)

    return DemographicsResult(
        male_ratio=male_ratio,
        female_ratio=female_ratio,
        grid=grid,
        analysis_target_count=analysis_target_count,
        classifiable_count=classifiable,
        unknown_count=unknown_count,
    )
