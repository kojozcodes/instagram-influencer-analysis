"""Regression guard for audience estimation against real Instagram Insights.

The client exported Instagram's official follower demographics for two accounts
they own and sent them as ground truth. These are the ONLY labelled points we
have, so they are pinned here: any change to the lexicons or the model that
pushes these back out of tolerance is a regression.

Tolerances are deliberately loose (±8pt gender, ±12pt per age band). They exist
to catch direction errors and centre-of-mass errors — the failures the first
model actually had — not to assert precision the method does not possess.
"""
from __future__ import annotations

import pytest

from app.analysis.demographics import demographics_from_counts, estimate_demographics
from app.models import AGE_BUCKETS, AccountData, AnalysisRow

# Bios as published by the accounts (both are repost/curation accounts).
YOGA_BIO = (
    "リポストを使って、ヨガの美しいお写真を"
    "ご紹介する【ヨガ美女】 #yoga_bijo コーナーです✨"
    "専門家が徹底比較｜商品比較メディア allmine"
)
SURF_BIO = (
    "リポストを使って、サーフガールの美しいお写真を"
    "ご紹介する【サーフィン美女】#surf_bijo コーナーです✨"
    "専門家が徹底比較｜商品比較メディア allmine"
)

# Instagram Insights, supplied by the client 2026-07-24.
GROUND_TRUTH = {
    "yoga_bijo": {
        "bio": YOGA_BIO, "name": "YOGA美女", "female": 59.1,
        "age": {"13-17": 0.0, "18-24": 0.9, "25-34": 15.5, "35-44": 32.1,
                "45-54": 31.7, "55-64": 15.5, "65+": 4.3},
    },
    "surf_bijo": {
        "bio": SURF_BIO, "name": "サーフ_bijo", "female": 14.9,
        "age": {"13-17": 0.1, "18-24": 1.2, "25-34": 12.4, "35-44": 24.9,
                "45-54": 34.4, "55-64": 21.8, "65+": 5.2},
    },
}

GENDER_TOLERANCE = 8.0
AGE_TOLERANCE = 12.0


@pytest.mark.parametrize("username", sorted(GROUND_TRUTH))
def test_gender_matches_official_insights(username):
    truth = GROUND_TRUTH[username]
    account = AccountData(
        username=username, display_name=truth["name"], biography=truth["bio"]
    )
    result = estimate_demographics(account)

    assert result.female_ratio is not None, "gender must not be unknown here"
    error = abs(result.female_ratio - truth["female"])
    assert error <= GENDER_TOLERANCE, (
        f"{username}: estimated {result.female_ratio}% female vs "
        f"{truth['female']}% actual ({error:.1f}pt off)"
    )


@pytest.mark.parametrize("username", sorted(GROUND_TRUTH))
def test_gender_direction_is_correct(username):
    """The failure that mattered most: reporting a male audience as female."""
    truth = GROUND_TRUTH[username]
    account = AccountData(
        username=username, display_name=truth["name"], biography=truth["bio"]
    )
    result = estimate_demographics(account)
    assert (result.female_ratio > 50) == (truth["female"] > 50), (
        f"{username}: estimate says "
        f"{'female' if result.female_ratio > 50 else 'male'}-dominant, "
        f"actual is {'female' if truth['female'] > 50 else 'male'}-dominant"
    )


@pytest.mark.parametrize("username", sorted(GROUND_TRUTH))
def test_age_distribution_is_in_range(username):
    truth = GROUND_TRUTH[username]
    account = AccountData(
        username=username, display_name=truth["name"], biography=truth["bio"]
    )
    result = estimate_demographics(account)

    for bucket in AGE_BUCKETS:
        estimated = (result.grid.get(f"female_{bucket}") or 0) + (
            result.grid.get(f"male_{bucket}") or 0
        )
        error = abs(estimated - truth["age"][bucket])
        assert error <= AGE_TOLERANCE, (
            f"{username} {bucket}: estimated {estimated:.1f}% vs "
            f"{truth['age'][bucket]}% actual ({error:.1f}pt off)"
        )


def test_age_buckets_match_instagram_bands():
    """Estimates are compared to Insights by eye, so the bands must line up."""
    assert AGE_BUCKETS == [
        "13-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"
    ]


def test_measured_demographics_are_marked_and_exclude_undeclared():
    """Instagram reports F/M/U; its own UI shows the split over F+M only."""
    counts = {
        ("25-34", "F"): 30, ("25-34", "M"): 10,
        ("35-44", "F"): 45, ("35-44", "M"): 15,
        ("35-44", "U"): 100,  # undeclared must not dilute the percentages
    }
    result = demographics_from_counts(counts)

    assert result.source == "measured"
    assert result.confidence == "実測"
    assert result.female_ratio == 75.0
    assert result.male_ratio == 25.0
    assert result.unknown_count == 100


def test_estimates_are_never_labelled_measured():
    account = AccountData(username="someone", biography="ヨガ講師です")
    assert estimate_demographics(account).source == "estimated"


def test_excel_always_states_whether_figures_are_measured_or_estimated():
    """Reading an estimate as Instagram's official number would be a serious
    misreading, so this column must never depend on INCLUDE_RELIABILITY."""
    from app import excel

    assert "属性データ種別" in excel.HEADERS
    assert "推定確度" in excel.HEADERS

    row = AnalysisRow(username="x", status="成功")
    row.demographics = estimate_demographics(
        AccountData(username="x", biography=YOGA_BIO)
    )
    values = excel._row_values(row)
    assert len(values) == len(excel.HEADERS), "row width must match header width"
    assert values[excel.HEADERS.index("属性データ種別")] == "推定値"

    row.demographics = demographics_from_counts({("25-34", "F"): 10})
    values = excel._row_values(row)
    assert values[excel.HEADERS.index("属性データ種別")] == "実測値（Instagram公式）"
    assert values[excel.HEADERS.index("推定確度")] == "実測"
