# Deploying to Vercel

> ⚠️ Vercel is serverless. This app was made compatible (stateless Excel
> download via an external store), but it needs an external Redis because the
> local filesystem and in-memory cache are **not** shared between serverless
> invocations. On a normal server (the Sakura VPS) none of this is needed —
> see `../DEPLOY.md`.

## 1. Create a free Redis (Upstash)
1. <https://upstash.com> → create a **Redis** database (free tier is fine).
2. Copy its connection URL — `rediss://default:<password>@<host>:<port>`.

## 2. Deploy
```bash
npm i -g vercel          # or: npx vercel
vercel login
vercel                   # first run: link/create the project
vercel --prod            # production deploy
```
`vercel.json` and `api/index.py` are already in the repo.

## 3. Set environment variables
Vercel → Project → Settings → Environment Variables (Production):

```
PROVIDER=graph
IG_USER_ID=<from .env>
GRAPH_ACCESS_TOKEN=<the 60-day token>
GRAPH_APP_ID=1367819675416012
REPORT_STORE=redis
REDIS_URL=<the Upstash rediss:// URL>
RECENT_POSTS_LIMIT=30
MAX_ANALYSIS_TARGETS=1000
```
Redeploy after setting them (`vercel --prod`).

## 4. Verify
Open the deployment URL, enter `yoga_bijo`, run the analysis, and download the
Excel. If the download 404s, `REPORT_STORE=redis` / `REDIS_URL` are not set.

## Caveats vs. the VPS
- **Rate-limit safety is weaker.** The in-process cache + budget guard
  (`app/providers/cache.py`) do NOT span serverless instances, so the shared
  Meta quota (~75-80 analyses/hour) is less protected. For real traffic the VPS
  is the correct target. To harden Vercel, the cache/usage counter would also
  need to move to Redis.
- Token refresh (`scripts/refresh_token.py`) can't run on Vercel — refresh the
  60-day token from any machine and update the `GRAPH_ACCESS_TOKEN` env var.
