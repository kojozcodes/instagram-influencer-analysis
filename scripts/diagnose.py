"""Check whether a token is ready for business_discovery. Read-only, no exchange.

Usage:
    python scripts/diagnose.py                 # uses GRAPH_ACCESS_TOKEN from .env
    python scripts/diagnose.py --token <TOK>   # check any token (e.g. a fresh short-lived one)

Prints a PASS/FAIL readiness summary. Never prints the full token.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

API = f"https://graph.facebook.com/{settings.graph_api_version}"
TARGET = "yoga_bijo"


def get(path: str, token: str, **params):
    params["access_token"] = token
    try:
        r = httpx.get(f"{API}/{path}", params=params, timeout=30)
        return r.status_code, r.json()
    except Exception as exc:  # network
        return 0, {"error": {"message": str(exc)}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=settings.graph_access_token)
    ap.add_argument("--ig-user-id", default=settings.ig_user_id)
    args = ap.parse_args()
    tok, ig_id = args.token, args.ig_user_id

    if not tok:
        print("No token. Pass --token or set GRAPH_ACCESS_TOKEN in .env")
        return 1

    print(f"Token: {tok[:8]}…{tok[-6:]} ({len(tok)} chars)\n")
    checks: list[tuple[str, bool, str]] = []

    # 1. token alive + identity
    sc, me = get("me", tok, fields="id,name")
    alive = sc == 200
    checks.append(("Token valid", alive,
                   f"{me.get('name')} (id {me.get('id')})" if alive
                   else me.get("error", {}).get("message", "")[:110]))
    if not alive:
        report(checks)
        return 1

    # 2. pages + which have an Instagram Business Account
    sc, acc = get("me/accounts", tok, fields="id,name,instagram_business_account{id,username}", limit=100)
    pages = acc.get("data", []) if sc == 200 else []
    print("Pages visible to this token:")
    linked = []
    for p in pages:
        iba = p.get("instagram_business_account")
        print(f"  - {p.get('name')} (id {p.get('id')}) -> IG: {iba.get('username') if iba else 'NONE'}")
        if iba:
            linked.append((p, iba))
    if not pages:
        print("  (none)")
    print()
    # NOTE: /me/accounts often returns EMPTY when the token was granted with
    # *granular* page permissions (target_ids), even though everything works.
    # So these are informational only — never treated as failures.
    if not pages:
        print("  note: empty list is normal with granular page grants — not an error.\n")

    # 3. the IG account itself must be readable
    sc, prof = get(ig_id, tok, fields="id,username,followers_count")
    prof_ok = sc == 200 and "username" in prof
    checks.append((f"Instagram account {ig_id} readable", prof_ok,
                   f"@{prof.get('username')} followers={prof.get('followers_count')}" if prof_ok
                   else prof.get("error", {}).get("message", "")[:110]))

    # 4. the real test
    sc, bd = get(ig_id, tok,
                 fields=f"business_discovery.username({TARGET})"
                        "{username,name,followers_count,media_count}")
    ok = sc == 200 and "business_discovery" in bd
    detail = ""
    if ok:
        b = bd["business_discovery"]
        detail = f"@{b.get('username')} followers={b.get('followers_count')} media={b.get('media_count')}"
    else:
        detail = bd.get("error", {}).get("message", "")[:110]
    checks.append((f"business_discovery on @{TARGET}", ok, detail))

    report(checks)
    return 0 if all(c[1] for c in checks) else 1


def report(checks):
    print("=" * 60)
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if detail:
            print(f"       {detail}")
    print("=" * 60)
    print("READY — the app can pull live data." if all(c[1] for c in checks)
          else "NOT READY — fix the FAIL above.")


if __name__ == "__main__":
    sys.exit(main())
