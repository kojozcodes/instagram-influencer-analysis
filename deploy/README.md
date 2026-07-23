# Deployment options

Three ready paths. The app code is identical for all three; only hosting differs.

| Option | Use when | How | Rate-limit safety |
|---|---|---|---|
| **1. Preview link** | client needs to click something *today* | `powershell -ExecutionPolicy Bypass -File deploy\preview_windows.ps1` (Windows) — prints a public `trycloudflare.com` URL | Full (single process) |
| **2. Sakura VPS** ⭐ | the real, permanent home (server already purchased) | `sudo DOMAIN=insta.beaus.net bash deploy/vps_setup.sh` — see `../DEPLOY.md` | Full (single process, `--workers 1`) |
| **3. Vercel** | only if the client insists on it | see `deploy/VERCEL.md` (needs a free Upstash Redis) | Weaker — cache/guard don't span serverless instances |

**Recommendation:** #1 to unblock the client now, then #2 as the permanent setup.
#3 works but is the weakest fit for a shared-token, rate-limited tool.

All three serve the same UI, produce the same Excel, and use the same live
Instagram credentials from the environment / `.env`.
