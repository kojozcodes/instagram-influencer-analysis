"""Vercel serverless entrypoint. Vercel's @vercel/python runtime serves the
ASGI `app` object exported here. All routes are directed to this file by
vercel.json.

For Vercel you MUST set (Project → Settings → Environment Variables):
    PROVIDER=graph
    IG_USER_ID, GRAPH_ACCESS_TOKEN, GRAPH_APP_ID   (the live credentials)
    REPORT_STORE=redis
    REDIS_URL=<Upstash Redis URL>   (free tier is fine)
Without REPORT_STORE=redis the Excel download will not work across serverless
invocations. See deploy/VERCEL.md.
"""
import sys
from pathlib import Path

# Ensure the project root (parent of this file) is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

# Vercel looks for a module-level `app` (ASGI) — re-exported here.
__all__ = ["app"]
