"""Provider interface: fetch public data for one Instagram account."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import AccountData


class InstagramProvider(ABC):
    @abstractmethod
    def fetch(self, username: str) -> AccountData:
        """Fetch public account data.

        Raises AccountError with a Japanese `reason` if the account cannot be
        retrieved (not found, private, not a business account, API error, etc.).
        """
        raise NotImplementedError
