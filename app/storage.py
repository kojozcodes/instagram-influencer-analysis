"""Storage for generated Excel reports, so /analyze and /download can live on
different processes/instances.

Three backends, chosen by the REPORT_STORE env var:
  - "file"   (default) — writes to OUTPUT_DIR. Correct for the VPS / a single
               process. This is the original, tested behaviour.
  - "redis"  — stores the bytes in Redis/Upstash with a TTL. Required for
               serverless (Vercel), where each request may hit a different
               instance and the local disk is ephemeral/read-only.
  - "memory" — process-local dict with TTL. Only for a single-worker demo.

The default keeps the VPS path unchanged; Vercel sets REPORT_STORE=redis.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Optional

from .config import settings

BACKEND = os.getenv("REPORT_STORE", "file").lower()
_TTL_SEC = int(os.getenv("REPORT_TTL_SEC", "3600"))

_mem: dict[str, tuple[bytes, str, float]] = {}
_lock = threading.Lock()


def _redis():
    import redis  # lazy import — only needed when REPORT_STORE=redis
    url = os.getenv("REDIS_URL") or os.getenv("KV_URL") or os.getenv("UPSTASH_REDIS_URL")
    if not url:
        raise RuntimeError("REPORT_STORE=redis but no REDIS_URL/KV_URL is set")
    return redis.from_url(url)


def save_report(file_id: str, data: bytes, filename: str) -> None:
    if BACKEND == "redis":
        r = _redis()
        r.setex(f"rpt:{file_id}", _TTL_SEC, data)
        r.setex(f"rpn:{file_id}", _TTL_SEC, filename.encode("utf-8"))
        return
    if BACKEND == "memory":
        with _lock:
            _mem[file_id] = (data, filename, time.time() + _TTL_SEC)
        return
    # file (default)
    (settings.output_dir / f"{file_id}.xlsx").write_bytes(data)
    (settings.output_dir / f"{file_id}.name").write_text(filename, encoding="utf-8")


def load_report(file_id: str) -> Optional[tuple[bytes, str]]:
    """Return (bytes, filename) or None if not found/expired."""
    if BACKEND == "redis":
        r = _redis()
        data = r.get(f"rpt:{file_id}")
        if data is None:
            return None
        name = r.get(f"rpn:{file_id}")
        return bytes(data), (name.decode("utf-8") if name else "analysis.xlsx")
    if BACKEND == "memory":
        with _lock:
            v = _mem.get(file_id)
            if not v or v[2] < time.time():
                _mem.pop(file_id, None)
                return None
            return v[0], v[1]
    # file (default)
    path = settings.output_dir / f"{file_id}.xlsx"
    if not path.exists():
        return None
    name_file = settings.output_dir / f"{file_id}.name"
    filename = name_file.read_text(encoding="utf-8") if name_file.exists() else "analysis.xlsx"
    return path.read_bytes(), filename
