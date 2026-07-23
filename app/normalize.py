"""Instagram account input parsing, normalization and validation (spec F1 / 6.1)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

MAX_ACCOUNTS = 20

# Instagram usernames: letters, numbers, periods, underscores; up to 30 chars.
# Cannot start or end with a period.
_USERNAME_RE = re.compile(r"^(?!\.)[A-Za-z0-9._]{1,30}(?<!\.)$")

_INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}
# Reserved first path segments that are not usernames.
_RESERVED_PATHS = {"p", "reel", "reels", "tv", "stories", "explore", "accounts"}


@dataclass
class NormalizeResult:
    accounts: list[str] = field(default_factory=list)          # valid, unique, ordered
    rejected: list[tuple[str, str]] = field(default_factory=list)  # (raw, reason)
    over_limit: bool = False  # True if more than MAX_ACCOUNTS valid accounts supplied


def _extract_from_url(token: str) -> str | None:
    """Return the username from an Instagram URL, or None if not extractable."""
    parsed = urlparse(token)
    if parsed.netloc.lower() not in _INSTAGRAM_HOSTS:
        return None
    segments = [s for s in parsed.path.split("/") if s]
    if not segments:
        return None
    first = segments[0]
    if first.lower() in _RESERVED_PATHS:
        return None
    return first


def normalize_one(raw: str) -> tuple[str | None, str | None]:
    """Normalize a single token.

    Returns (username, None) on success, or (None, reason) on failure.
    """
    token = raw.strip()
    if not token:
        return None, "空入力"

    # URL form
    if "instagram.com" in token.lower():
        extracted = _extract_from_url(token if "//" in token else "https://" + token)
        if extracted is None:
            return None, "InstagramのURL形式が不正です"
        token = extracted

    # Strip a leading @
    token = token.lstrip("@").strip()
    # Strip a trailing slash left over from a bare "instagram.com/name/"
    token = token.rstrip("/")

    if not token:
        return None, "空入力"

    username = token.lower()
    if not _USERNAME_RE.match(username):
        return None, "不正な文字またはアカウント形式です"

    return username, None


def normalize_input(raw_text: str) -> NormalizeResult:
    """Parse a free-form textarea (newline and/or comma separated) into accounts."""
    result = NormalizeResult()
    seen: set[str] = set()

    # Split on newlines and commas.
    tokens = re.split(r"[\n,]+", raw_text or "")

    for raw in tokens:
        if not raw.strip():
            continue
        username, reason = normalize_one(raw)
        if username is None:
            result.rejected.append((raw.strip(), reason or "不正な入力"))
            continue
        if username in seen:
            # Duplicate: silently removed per spec ("重複アカウントは自動除外").
            continue
        seen.add(username)
        result.accounts.append(username)

    if len(result.accounts) > MAX_ACCOUNTS:
        result.over_limit = True
        result.accounts = result.accounts[:MAX_ACCOUNTS]

    return result
