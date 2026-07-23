"""Application configuration, loaded from environment variables (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so we don't need an extra dependency."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Do not override variables already set in the real environment.
        os.environ.setdefault(key, value)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_load_dotenv(_PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    provider: str = os.getenv("PROVIDER", "mock").lower()
    graph_api_version: str = os.getenv("GRAPH_API_VERSION", "v21.0")
    ig_user_id: str = os.getenv("IG_USER_ID", "")
    graph_access_token: str = os.getenv("GRAPH_ACCESS_TOKEN", "")
    recent_posts_limit: int = int(os.getenv("RECENT_POSTS_LIMIT", "30"))
    max_analysis_targets: int = int(os.getenv("MAX_ANALYSIS_TARGETS", "1000"))

    @property
    def project_root(self) -> Path:
        return _PROJECT_ROOT


settings = Settings()
