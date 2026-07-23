"""Data provider factory.

The live provider is wrapped in CachingProvider: every user of the tool shares
one Meta token and therefore one hourly quota, so repeated lookups are served
from cache and calls are throttled as the quota fills.
"""
from __future__ import annotations

from ..config import settings
from .base import InstagramProvider

_provider: InstagramProvider | None = None


def get_provider() -> InstagramProvider:
    """Return the shared provider instance (cache must be shared across requests)."""
    global _provider
    if _provider is None:
        if settings.provider == "graph":
            from .cache import CachingProvider
            from .graph_api import GraphAPIProvider
            _provider = CachingProvider(GraphAPIProvider())
        else:
            from .mock import MockProvider
            _provider = MockProvider()
    return _provider
