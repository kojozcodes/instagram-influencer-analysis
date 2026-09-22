# Deployment Guide — Meta App + Sakura VPS

Two parts: (A) get Instagram Graph API access, (B) deploy on Sakura VPS.

---

## A. Meta / Instagram Graph API setup

The client prepares a **Facebook account** and an **Instagram Business or
Creator account**. The IG account must be linked to a Facebook Page.

1. **Convert the IG account to Business/Creator** (IG app → Settings → Account
   type) and link it to a Facebook Page.
2. Go to <https://developers.facebook.com> → **My Apps → Create App** → type
   **Business**.
3. Add the **Instagram Graph API** product.
4. Under **App roles**, add the client's Facebook account (and ours during dev)
   as admin/tester.
5. Get an access token via **Graph API Explorer** with **all four** of these
   permissions — see the ⚠️ note below, the 4th one is easy to miss:
   ```
   instagram_basic
   instagram_manage_insights     <-- REQUIRED by business_discovery
   pages_read_engagement
   pages_show_list
   ```
   In the consent dialog, select the **Facebook Page** the Instagram account is
   connected to (not just any Page), and the Instagram account itself.
6. Find the **IG User ID** of the connected account:
   `GET /me/accounts` → the Page → `?fields=instagram_business_account`.
7. **Exchange the short-lived token for a long-lived (~60 day) one** and write it
   into `.env` in one step:
   ```bash
   python scripts/refresh_token.py --app-id <APP_ID> --app-secret <SECRET> --token <SHORT_TOKEN>
   ```
8. Verify everything with:
   ```bash
   python scripts/diagnose.py
   ```

**Notes / hard-won gotchas**
- ⚠️ **`instagram_manage_insights` is mandatory.** Without it `business_discovery`
  fails with `(#10) Application does not have permission for this action` — even
  though profile and media reads still succeed. This is the single most common
  cause of that error.
- ⚠️ Tokens from Graph API Explorer are **short-lived (~1 hour)**. Exchange them
  immediately (step 7); don't send them between people first.
- ⚠️ Permissions are **baked into the token at creation**. Adding a permission in
  the App Dashboard does nothing to an existing token — a **new** token must be
  generated. If the "再リンク / Re-link" dialog appears, choose **Edit settings**,
  not Re-link (Re-link restores the previous, incomplete permission set).
- ℹ️ `GET /me/accounts` can return an **empty list** even when everything works
  (granular page grants). Judge success by `business_discovery`, not by that call.
- `business_discovery` only reads **public Business/Creator** accounts. Personal
  or private targets return an error row (expected).
- **App Review is NOT required** for `business_discovery` while the app is used
  by users who have a role on it (Development mode / Standard Access). If the tool
  is later opened to the general public, Live mode + App Review + Business
  Verification will be needed — allow significant lead time for that.
- Reels view counts are generally **not exposed** for third-party accounts, so
  those columns may be blank. Expected, per the spec's "where obtainable".
- Token refresh: long-lived tokens last ~60 days. Re-run `scripts/refresh_token.py`
  before expiry (a fresh short-lived token is needed as input).

## Quick API smoke test

```bash
curl -G "https://graph.facebook.com/v21.0/<IG_USER_ID>" \
  --data-urlencode "fields=business_discovery.username(yoga_bijo){username,followers_count,media_count}" \
  --data-urlencode "access_token=<TOKEN>"
```

---

## B. Sakura VPS (Ubuntu/Linux) deployment

Assumes Ubuntu 22.04+, a domain pointing at the VPS, ports 80/443 open.

### 1. System packages

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nginx
```

### 2. App

```bash
sudo mkdir -p /opt/insta && sudo chown $USER /opt/insta
cd /opt/insta
# copy the project here (git clone / scp)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env    # set PROVIDER=graph, IG_USER_ID, GRAPH_ACCESS_TOKEN
```

### 3. systemd service — `/etc/systemd/system/insta.service`

```ini
[Unit]
Description=Instagram Influencer Analysis
After=network.target

[Service]
WorkingDirectory=/opt/insta
ExecStart=/opt/insta/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
User=www-data
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now insta
```

### 4. nginx reverse proxy — `/etc/nginx/sites-available/insta`

```nginx
server {
    listen 80;
    server_name your-domain.example.jp;

    client_max_body_size 2m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/insta /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 5. SSL (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.example.jp
```

### 6. Access control (no login in v1 — spec §14)

Keep the URL private. If stronger control is needed, add HTTP basic-auth or an
`allow`/`deny` IP block in the nginx `location`, e.g.:

```nginx
location / {
    allow 203.0.113.0/24;   # client office IP
    deny all;
    proxy_pass http://127.0.0.1:8000;
    # ...proxy headers as above
}
```

### ⚠️ Rate limits — read before launch

Every user of this tool shares **one** Meta access token, so the whole system
shares **one hourly quota**. This is a hard Meta limit, not a design choice.

**Measured capacity (2026-07, live API):**

| Measurement | Value |
|---|---|
| 25 full analyses consumed | **32%** of the hourly quota |
| Practical ceiling | **~75-80 account analyses per hour, system-wide** |
| One user submitting the 20-account maximum | **~25%** of the hour |

So roughly **4 heavy users per hour** will exhaust the quota for everyone.
The binding metric is `total_time` in Meta's `x-app-usage` header — **not**
call count, which stays low and looks deceptively healthy.

**Built-in protections** (`app/providers/cache.py`):
- **Cache** — the same account requested again within 60 minutes is served from
  memory at **zero quota cost**. Since many users analyse the same popular
  influencers, this is the largest real-world saving.
- **Budget guard** — slows down above 60% usage; above 85% it returns a clear
  Japanese message instead of letting Meta hard-fail mid-report. Already-cached
  accounts keep working even while throttled.

**⚠️ Run a single worker.** The cache is per-process, so `--workers 2` would give
each worker its own cache and roughly halve the benefit. The `ExecStart` above
pins `--workers 1` deliberately. If higher throughput is ever needed, move the
cache to Redis rather than adding workers.

**If traffic grows beyond this**, the options are: raise `CACHE_TTL_MINUTES`,
add a job queue so analyses run in the background, or request higher limits from
Meta (requires App Review / Advanced Access).

### 8. Token renewal without a redeploy — `/admin/token`

The 60-day Meta token can be replaced from the browser:

1. Set in `.env` (then `systemctl restart insta`):
   `GRAPH_APP_ID`, `GRAPH_APP_SECRET` (Meta app dashboard → 設定 → ベーシック → app secret),
   `ADMIN_PASSWORD` (any strong password; give it to the client).
2. Make sure `data/` is writable by the service user (`vps_setup.sh` does this).
3. The client opens `https://<domain>/admin/token`, follows the 4 on-page steps
   (Graph API Explorer → Generate Access Token → copy), pastes the token with the
   password. The server exchanges it for a 60-day token, verifies it against the
   IG account, saves it to `data/token.json` and uses it immediately.

The input screen shows the expiry date and warns from 14 days before; when the
token has expired it says so and links to the page. The env var
`GRAPH_ACCESS_TOKEN` is only the initial/fallback token: a saved `data/token.json`
takes precedence on start-up.

### 7. Housekeeping

Generated Excel files land in `generated/`. Add a cron job to purge old files:

```bash
# purge files older than 1 day, daily at 03:00
0 3 * * * find /opt/insta/generated -type f -mmin +1440 -delete
```
