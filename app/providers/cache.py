"""Caching + rate-limit protection wrapper around any InstagramProvider.

Why this exists: every user of the tool shares ONE Meta access token, so the
whole system shares one hourly quota. Measured cost is roughly 75-80 account
analyses per hour before Meta starts throttling (the binding metric is
`total_time`, not call count).

Two protections:
  1. CACHE  - repeated lookups of the same account inside CACHE_TTL_MINUTES are
              served from memory, costing zero quota. Influencer stats do not
              meaningfully change minute to minute, so this is safe and it is
              the single biggest saving in real use (many users analysing the
              same popular accounts).
  2. BUDGET - tracks Meta's reported x-app-usage. Above USAGE_WARN_PCT we slow
              down; above USAGE_STOP_PCT we refuse new calls with a clear
              Japanese message rather than letting Meta hard-fail the request.
"""
from __future__ import annotations

import threading
import time

from ..models import AccountData, AccountError

CACHE_TTL_MINUTES = 60
USAGE_WARN_PCT = 60      # start throttling
USAGE_STOP_PCT = 85      # stop before Meta cuts us off
THROTTLE_SLEEP_SEC = 2.0


class _Entry:
    __slots__ = ("data", "ts")

    def __init__(self, data: AccountData, ts: float):
        self.data = data
        self.ts = ts


class CachingProvider:
    """Wraps a provider with an in-memory TTL cache and a usage guard."""

    def __init__(self, inner):
        self._inner = inner
        self._cache: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    # -- usage tracking -------------------------------------------------
    @property
    def _usage(self) -> int:
        """Highest Meta usage percentage seen so far (0-100)."""
        return getattr(self._inner, "last_usage_pct", 0) or 0

    # -- main entry point ------------------------------------------------
    def fetch(self, username: str) -> AccountData:
        key = username.lower()
        now = time.time()

        with self._lock:
            hit = self._cache.get(key)
            if hit and (now - hit.ts) < CACHE_TTL_MINUTES * 60:
                self.hits += 1
                return hit.data

        usage = self._usage
        if usage >= USAGE_STOP_PCT:
            raise AccountError(
                "API利用上限に近づいたため、一時的に分析を停止しました。"
                "しばらく時間をおいて再実行してください。"
            )
        if usage >= USAGE_WARN_PCT:
            time.sleep(THROTTLE_SLEEP_SEC)

        data = self._inner.fetch(username)

        with self._lock:
            self._cache[key] = _Entry(data, now)
            self.misses += 1
        return data

    # -- introspection ---------------------------------------------------
    def stats(self) -> dict:
        return {
            "cached_accounts": len(self._cache),
            "hits": self.hits,
            "misses": self.misses,
            "usage_pct": self._usage,
        }
