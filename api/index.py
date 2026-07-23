"""Vercel serverless entrypoint. Vercel's @vercel/python runtime serves the
ASGI `app` object exported here; vercel.json routes all requests to this file.

The app is stateless (the Excel is delivered inline as a base64 data URI), so no
database or external store is needed. Just set these environment variables in
the Vercel project (Settings -> Environment Variables):

    PROVIDER=graph
    IG_USER_ID
    GRAPH_ACCESS_TOKEN
    GRAPH_APP_ID
    RECENT_POSTS_LIMIT=30
    MAX_ANALYSIS_TARGETS=1000

See deploy/VERCEL.md.
"""
import sys
from pathlib import Path

# Ensure the project root (parent of this file) is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

# Vercel looks for a module-level `app` (ASGI) — re-exported here.
__all__ = ["app"]
