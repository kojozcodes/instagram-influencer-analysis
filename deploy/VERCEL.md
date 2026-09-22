# Deploying to Vercel

The app is **stateless** — the Excel report is delivered inline (base64 data URI
in the result page), so there is no database, no external store, and no file
system to configure. Deployment is just: import the repo, set the credentials,
deploy.

> Note: Vercel is serverless, so the in-process cache + rate-limit guard
> (`app/providers/cache.py`) do NOT span instances — the shared Meta quota
> (~75-80 analyses/hour) is less protected than on the single-process VPS. For
> real traffic the Sakura VPS is the better home (see `../DEPLOY.md`). Vercel is
> ideal for a review/preview deployment.

## 1. Import the repo
1. <https://vercel.com> → **Add New… → Project**.
2. **Import** the GitHub repo (authorize Vercel to access it if prompted).
3. Framework preset: **Other**. Leave build/output settings default —
   `vercel.json` and `api/index.py` already configure the Python runtime.
4. Don't deploy yet — add the environment variables first (next step).

## 2. Environment variables
Project → **Settings → Environment Variables** (Production), add:

```
PROVIDER=graph
IG_USER_ID=<from .env>
GRAPH_ACCESS_TOKEN=<the 60-day token>
GRAPH_APP_ID=1367819675416012
RECENT_POSTS_LIMIT=30
MAX_ANALYSIS_TARGETS=1000
```

## 3. Deploy
Click **Deploy** (or **Deployments → Redeploy** if you added the variables after
the first deploy).

## 4. Verify
Open the deployment URL, enter `yoga_bijo`, run the analysis, and download the
Excel. If analysis returns errors, re-check the environment variables.

## Token refresh (self-service page)

The app has a renewal page at `/admin/token`: the client pastes a fresh Graph API
Explorer token and the server exchanges it for a 60-day token. For that, also set
`GRAPH_APP_SECRET` and `ADMIN_PASSWORD` in the env vars. **On Vercel the renewed
token is not persisted** (no writable disk) — it is used until the next cold start,
so still update `GRAPH_ACCESS_TOKEN` here afterwards. The VPS keeps it in
`data/token.json` and needs nothing else.

## Token refresh (manual)
The 60-day token can't be refreshed from Vercel. Run
`python scripts/refresh_token.py ...` from any machine and paste the new
`GRAPH_ACCESS_TOKEN` into the Vercel env vars, then redeploy.
