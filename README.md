# Instagram Influencer Analysis System / Instagramインフルエンサー分析システム

Internal web tool for 株式会社ビューズ. Enter up to 20 Instagram accounts, run
analysis, and download an Excel report with engagement metrics and **estimated**
follower demographics.

> Demographics are **estimated** from each account's own public signals (bio,
> display name, hashtags, captions) — not from real follower data, which
> Instagram does not expose. See the spec and `app/analysis/demographics.py`.

## Architecture

```
app/
  main.py            FastAPI routes: input screen, /analyze, /download
  config.py          .env-driven settings
  models.py          AccountData, AnalysisRow, result dataclasses
  normalize.py       input parsing / normalization / validation (F1)
  pipeline.py        per-account orchestration; isolates failures (F2/§11)
  excel.py           .xlsx generation, 24 Japanese columns (§10)
  analysis/
    engagement.py    engagement rate (F4)
    demographics.py  gender/age estimation (F5/§8/§9)
    keywords.py      JP/EN keyword dictionaries (edit to improve accuracy)
  providers/
    base.py          provider interface
    mock.py          fixtures — runs the whole app WITHOUT Meta credentials
    graph_api.py     real Instagram Graph API (business_discovery)
  templates/         input + result screens
tests/               pytest suite (18 tests)
```

## Data source

Uses the official **Instagram Graph API `business_discovery`** endpoint. Our own
connected IG Business/Creator account looks up *public* Business/Creator accounts
by username and reads profile + recent media (likes/comments). Personal/private
accounts and follower demographics are not available via this API — hence the
estimation approach and per-account error handling.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows;  source .venv/bin/activate on Linux
pip install -r requirements.txt
cp .env.example .env             # then edit
```

### Run (development, no credentials needed)

`.env` ships with `PROVIDER=mock`, so the full app runs on fixture data:

```bash
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

Try accounts: `yoga_bijo`, `muscle_taro`, `cafe_days` (success),
`private_account`, `nonexistent_user` (error rows).

### Switch to live Instagram data

In `.env`:

```
PROVIDER=graph
IG_USER_ID=<your connected IG business account id>
GRAPH_ACCESS_TOKEN=<long-lived token — see permissions below>
```

The token must be generated with **all four** of these permissions:

```
instagram_basic
instagram_manage_insights     <-- REQUIRED by business_discovery
pages_read_engagement
pages_show_list
```

> ⚠️ Without `instagram_manage_insights`, `business_discovery` fails with
> `(#10) Application does not have permission for this action`, even though
> profile/media reads still work. Permissions are baked into a token when it is
> created — adding one later requires generating a **new** token.

Helper scripts:

```bash
# exchange a short-lived token for a 60-day one, write it to .env, and verify
python scripts/refresh_token.py --app-id <APP_ID> --app-secret <SECRET> --token <SHORT_TOKEN>

# check readiness (token -> pages -> IG link -> business_discovery)
python scripts/diagnose.py
```

No other code changes. See `DEPLOY.md` for the Meta app + Sakura VPS setup.

### Renewing the token from the browser (`/admin/token`)

Meta tokens last 60 days. Instead of editing `.env` every time, the client can
open `/admin/token`, follow the four on-page steps (Graph API Explorer →
Generate Access Token → copy) and paste the token. The server exchanges it for a
60-day token, verifies it and starts using it immediately; on a VPS it is saved
to `data/token.json` and survives restarts. Needs in `.env`:

```
GRAPH_APP_ID=<Meta app id>
GRAPH_APP_SECRET=<Meta app dashboard → 設定 → ベーシック>
ADMIN_PASSWORD=<password for the page>
```

The input screen shows the expiry date, warns from 14 days before, and links to
the page once the token has expired.

## Tests

```bash
python -m pytest -q
```

## Excel output columns (§10)

24 columns with Japanese headers: account/display name/URL, follower count,
estimated male & female ratios, 5 age-band ratios × 2 genders, analysis target /
classifiable / unknown counts, avg likes, avg comments, engagement rate, status,
error reason. A top note states the values are estimates (推定).
