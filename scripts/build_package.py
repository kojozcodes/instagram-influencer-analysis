"""Build the delivery zip for the hosting side and refuse to ship credentials.

    python scripts/build_package.py            -> ../instagram_analysis_system_<date>.zip

Ships: app/ scripts/ tests/ deploy/ + the docs, requirements and .env.example.
Never ships: .env, data/ (saved tokens), validation_data/, caches, generated files.
Every text file is scanned for token-shaped strings and 32-hex secrets before zipping.
"""
from __future__ import annotations

import re
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT.parent / f"instagram_analysis_system_{date.today():%Y%m%d}.zip"
INCLUDE_DIRS = ["app", "scripts", "tests", "deploy"]
INCLUDE_FILES = ["README.md", "DEPLOY.md", "requirements.txt", ".env.example", ".gitignore",
                 "vercel.json", "api/index.py"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", "data", "generated"}
LEAK = [re.compile(r"EAA[A-Za-z0-9]{80,}"),                   # Meta access token
        re.compile(r"(?i)secret[^\n]{0,20}[0-9a-f]{32}")]     # app secret next to the word


def files():
    for d in INCLUDE_DIRS:
        for p in (ROOT / d).rglob("*"):
            if p.is_file() and not (SKIP_PARTS & set(p.relative_to(ROOT).parts)) and p.suffix != ".pyc":
                yield p
    for f in INCLUDE_FILES:
        p = ROOT / f
        if p.exists():
            yield p


def main() -> int:
    picked = sorted(set(files()))
    leaks = []
    for p in picked:
        if p.suffix in {".py", ".md", ".html", ".txt", ".example", ".sh", ".json", ".gitignore"} or p.name.startswith("."):
            text = p.read_text(encoding="utf-8", errors="ignore")
            for rx in LEAK:
                if rx.search(text):
                    leaks.append(str(p.relative_to(ROOT)))
    if leaks:
        print("REFUSING TO PACKAGE - credential-looking strings in:", *leaks, sep="\n  ")
        return 1
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in picked:
            z.write(p, p.relative_to(ROOT).as_posix())
    names = [p.relative_to(ROOT).as_posix() for p in picked]
    assert ".env" not in names and not any(n.startswith("data/") for n in names)
    print(f"{OUT}  ({OUT.stat().st_size // 1024} KB, {len(names)} files)")
    for n in names:
        print("  ", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
