#!/usr/bin/env bash
set -uo pipefail

IP=139.155.146.41
META=$(curl -s --max-time 5 http://metadata.tencentyun.com/latest/meta-data/public-ipv4 || true)
[ -n "$META" ] && IP="$META"
echo "public IP (from Tencent metadata): $IP"

echo
echo "=== 0) reinstall corrected systemd unit (StartLimit* moved to [Unit]) ==="
sudo tee /etc/systemd/system/agent.service >/dev/null <<'UNIT'
[Unit]
Description=Agent API (FastAPI + hierarchical collaboration)
Documentation=file:///opt/agent/docs/DEPLOY.md
After=network-online.target
Wants=network-online.target
StartLimitBurst=5
StartLimitIntervalSec=120

[Service]
Type=simple
User=agent
Group=agent
WorkingDirectory=/opt/agent
ExecStart=/opt/agent/.venv/bin/python scripts/run_server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=agent
KillSignal=SIGINT
TimeoutStopSec=30
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl restart agent
sleep 4
WARNS=$(sudo journalctl -u agent -n 30 --no-pager | grep -ci "unknown key" || true)
echo "unit warnings in journal: $WARNS  (0 = clean)"
echo "service active: $(systemctl is-active agent)"

echo
echo "=== 1) install nginx ==="
sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx
nginx -v 2>&1

echo
echo "=== 2) HTTP-only config (needed before ACME can validate) ==="
sudo rm -f /etc/nginx/sites-enabled/default
sudo mkdir -p /var/www/certbot
sudo tee /etc/nginx/conf.d/agent.conf >/dev/null <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $IP;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 'probe-ok'; }
}
NGINX
sudo nginx -t && sudo systemctl reload nginx
curl -s -o /dev/null -w "local probe http://127.0.0.1/ -> %{http_code}\n" http://127.0.0.1/

echo
echo "=== 3) certbot via pip (not snap: snapcraft is unreliable from mainland) ==="
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv
[ -x /opt/certbot/bin/python ] || sudo python3 -m venv /opt/certbot
sudo /opt/certbot/bin/pip install -q -U pip
sudo /opt/certbot/bin/pip install -q -i https://mirrors.cloud.tencent.com/pypi/simple certbot
/opt/certbot/bin/certbot --version

echo
echo "=== 4) issue IP certificate (needs certbot >= 5.4 for webroot+IP) ==="
sudo /opt/certbot/bin/certbot certonly --non-interactive --agree-tos \
  --register-unsafely-without-email \
  --preferred-profile shortlived \
  --webroot --webroot-path /var/www/certbot \
  --ip-address "$IP" 2>&1 | tail -30

echo
echo "=== 5) what is on disk ==="
sudo ls /etc/letsencrypt/live/ 2>&1
sudo ls -l "/etc/letsencrypt/live/$IP/" 2>&1 | head -8
echo "=== DONE ==="
