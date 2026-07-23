"""Exchange a short-lived Graph API token for a long-lived one, update .env, verify.

Also used for the ~60-day token refresh later.

Usage:
    python scripts/refresh_token.py --app-id <ID> --app-secret <SECRET> --token <SHORT_TOKEN>

Reads APP_ID from .env (GRAPH_APP_ID) if --app-id is omitted.
Never prints the full token.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
API_VERSION = "v21.0"
TEST_ACCOUNT = "yoga_bijo"


def mask(tok: str) -> str:
    return f"{tok[:8]}…{tok[-6:]} ({len(tok)} chars)" if tok else "(empty)"


def read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def write_env_value(key: str, value: str) -> None:
    """Update (or append) a single key in .env, leaving everything else intact."""
    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(f"{key}={value}", text)
    else:
        text = text.rstrip("\n") + f"\n{key}={value}\n"
    ENV.write_text(text, encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--app-id")
    p.add_argument("--app-secret", required=True)
    p.add_argument("--token", required=True, help="short-lived token from Graph API Explorer")
    args = p.parse_args()

    env = read_env()
    app_id = args.app_id or env.get("GRAPH_APP_ID", "")
    ig_user_id = env.get("IG_USER_ID", "")
    if not app_id:
        print("ERROR: no app id (pass --app-id or set GRAPH_APP_ID in .env)")
        return 1

    base = f"https://graph.facebook.com/{API_VERSION}"

    # 1) exchange short-lived -> long-lived
    print("1) Exchanging for a long-lived token…")
    r = httpx.get(f"{base}/oauth/access_token", params={
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": args.app_secret,
        "fb_exchange_token": args.token,
    }, timeout=30)
    if r.status_code != 200:
        print("   FAILED:", r.json().get("error", {}).get("message", r.text[:300]))
        return 1
    payload = r.json()
    long_token = payload.get("access_token", "")
    expires_in = payload.get("expires_in")
    print("   OK ->", mask(long_token),
          f"| expires_in: {expires_in}s (~{int(expires_in)//86400}d)" if expires_in else "")

    # 2) verify with a real business_discovery call
    print(f"2) Verifying with business_discovery on @{TEST_ACCOUNT}…")
    if not ig_user_id:
        print("   SKIPPED: IG_USER_ID missing from .env")
    else:
        fields = (f"business_discovery.username({TEST_ACCOUNT})"
                  "{username,name,followers_count,media_count}")
        v = httpx.get(f"{base}/{ig_user_id}", params={
            "fields": fields, "access_token": long_token}, timeout=30)
        if v.status_code != 200:
            print("   FAILED:", v.json().get("error", {}).get("message", v.text[:300]))
            return 1
        bd = v.json().get("business_discovery", {})
        print(f"   OK -> @{bd.get('username')} | {bd.get('name')} | "
              f"followers={bd.get('followers_count')} | media={bd.get('media_count')}")

    # 3) persist
    write_env_value("GRAPH_ACCESS_TOKEN", long_token)
    write_env_value("GRAPH_APP_ID", app_id)
    write_env_value("PROVIDER", "graph")
    print("3) .env updated (PROVIDER=graph, long-lived token stored).")
    print("\nDone. Run:  python -m uvicorn app.main:app --reload")
    return 0


if __name__ == "__main__":
    sys.exit(main())
