import pytest

from app.models import AccountData, AccountError
from app.providers.cache import CachingProvider


class FakeProvider:
    """Counts calls so we can prove the cache prevents API hits."""

    def __init__(self, usage=0):
        self.calls = 0
        self.last_usage_pct = usage

    def fetch(self, username: str) -> AccountData:
        self.calls += 1
        return AccountData(username=username, followers_count=100)


def test_repeat_lookup_uses_cache_not_api():
    inner = FakeProvider()
    p = CachingProvider(inner)
    p.fetch("yoga_bijo")
    p.fetch("yoga_bijo")
    p.fetch("yoga_bijo")
    assert inner.calls == 1, "only the first lookup should hit the API"
    assert p.hits == 2


def test_cache_is_case_insensitive():
    inner = FakeProvider()
    p = CachingProvider(inner)
    p.fetch("Yoga_Bijo")
    p.fetch("yoga_bijo")
    assert inner.calls == 1


def test_different_accounts_are_fetched_separately():
    inner = FakeProvider()
    p = CachingProvider(inner)
    p.fetch("a_one")
    p.fetch("b_two")
    assert inner.calls == 2


def test_stops_before_meta_cuts_us_off():
    """At high quota usage we refuse politely instead of letting Meta hard-fail."""
    inner = FakeProvider(usage=90)
    p = CachingProvider(inner)
    with pytest.raises(AccountError) as exc:
        p.fetch("yoga_bijo")
    assert "API利用上限" in exc.value.reason
    assert inner.calls == 0, "should not call the API when over budget"


def test_cached_accounts_still_served_when_over_budget():
    """A cached account costs no quota, so it must still work when throttled."""
    inner = FakeProvider(usage=0)
    p = CachingProvider(inner)
    p.fetch("yoga_bijo")          # populate cache
    inner.last_usage_pct = 95     # now over budget
    got = p.fetch("yoga_bijo")    # must not raise
    assert got.username == "yoga_bijo"
    assert inner.calls == 1
