#!/usr/bin/env bash
# One-shot deploy for the Sakura VPS (Ubuntu 22.04+). Run as a sudo-capable user.
#
#   1. copy the project to the server (git clone or scp) into /opt/insta
#   2. cd /opt/insta && cp .env.example .env   # then fill in the live credentials
#   3. sudo DOMAIN=insta.beaus.net bash deploy/vps_setup.sh
#
# Idempotent: safe to re-run. See DEPLOY.md for the manual walkthrough.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/insta}"
DOMAIN="${DOMAIN:-}"
SERVICE=insta

echo "==> app dir: $APP_DIR   domain: ${DOMAIN:-<none, HTTP only>}"
[ -f "$APP_DIR/app/main.py" ] || { echo "ERROR: $APP_DIR/app/main.py not found — copy the project there first."; exit 1; }
[ -f "$APP_DIR/.env" ]        || { echo "ERROR: $APP_DIR/.env missing — cp .env.example .env and fill it in."; exit 1; }

echo "==> installing system packages"
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip nginx

echo "==> python venv + deps"
cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "==> quick self-check (readiness against the live token)"
.venv/bin/python scripts/diagnose.py || echo "  (diagnose reported an issue — check .env; continuing)"

echo "==> systemd service"
sudo tee /etc/systemd/system/$SERVICE.service >/dev/null <<UNIT
[Unit]
Description=Instagram Influencer Analysis
After=network.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
User=www-data
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT
mkdir -p "$APP_DIR/data"                      # renewed tokens are saved here (/admin/token)
sudo chown -R www-data:www-data "$APP_DIR"
sudo systemctl daemon-reload
sudo systemctl enable --now $SERVICE
sudo systemctl restart $SERVICE

echo "==> nginx reverse proxy"
sudo tee /etc/nginx/sites-available/$SERVICE >/dev/null <<NGINX
server {
    listen 80;
    server_name ${DOMAIN:-_};
    client_max_body_size 2m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINX
sudo ln -sf /etc/nginx/sites-available/$SERVICE /etc/nginx/sites-enabled/$SERVICE
sudo nginx -t && sudo systemctl reload nginx

if [ -n "$DOMAIN" ]; then
  echo "==> SSL via Let's Encrypt for $DOMAIN"
  sudo apt-get install -y certbot python3-certbot-nginx
  sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email || \
    echo "  (certbot failed — ensure DNS for $DOMAIN points here, then: sudo certbot --nginx -d $DOMAIN)"
fi

echo
echo "==> DONE. Status:"
sudo systemctl --no-pager status $SERVICE | head -5
echo "Visit: http://${DOMAIN:-<server-ip>}   (https once certbot succeeds)"
