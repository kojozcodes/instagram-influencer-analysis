"""Analysis orchestration (spec F2): analyze accounts, isolate per-account errors."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .analysis.demographics import demographics_from_counts, estimate_demographics
from .analysis.metrics import calculate_metrics
from .config import settings
from .models import AccountError, AnalysisRow
from .providers import get_provider


def _demographics_for(account, username: str, provider):
    """Exact demographics if Instagram will give them to us, else an estimate.

    Only accounts connected to our app expose follower_demographics; a provider
    without the method (mock) or a failed lookup falls back to estimation.
    """
    getter = getattr(provider, "fetch_measured_demographics", None)
    if getter is not None:
        try:
            counts = getter(username)
        except Exception:
            counts = None
        if counts:
            return demographics_from_counts(counts)
    return estimate_demographics(account, settings.max_analysis_targets)


def analyze_account(username: str, provider=None) -> AnalysisRow:
    """Analyze a single account. Never raises — failures become an error row."""
    provider = provider or get_provider()
    row = AnalysisRow(
        username=username,
        account_url=f"https://www.instagram.com/{username}",
    )
    try:
        account = provider.fetch(username)
        row.display_name = account.display_name
        row.account_url = account.account_url or row.account_url
        row.followers_count = account.followers_count
        row.profile_text = account.biography
        # Prefer Instagram's own figures when the account is connected to our
        # app — those are exact. Everything else can only be estimated.
        row.demographics = _demographics_for(account, username, provider)
        row.metrics = calculate_metrics(account)
        row.status = "成功"
    except AccountError as exc:
        row.status = "エラー"
        row.error_reason = exc.reason
    except Exception as exc:  # unexpected — still isolate it
        row.status = "エラー"
        row.error_reason = f"分析処理に失敗しました: {exc.__class__.__name__}"
    return row


# Each account costs ~3s (profile + 30 media), so 20 sequential accounts would
# run ~60s and risk hitting the serverless execution limit. Fetches are network
# -bound and the provider's cache is lock-guarded, so they overlap safely. The
# cap keeps us from opening 20 simultaneous connections to Meta.
MAX_CONCURRENT_FETCHES = 5


def analyze_accounts(usernames: list[str]) -> list[AnalysisRow]:
    provider = get_provider()
    if len(usernames) <= 1:
        return [analyze_account(u, provider) for u in usernames]

    workers = min(MAX_CONCURRENT_FETCHES, len(usernames))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # map preserves input order, which the Excel and the UI both rely on
        return list(pool.map(lambda u: analyze_account(u, provider), usernames))
