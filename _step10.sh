#!/usr/bin/env bash
set -uo pipefail
IP=139.155.146.41

echo "=== kill the randomly-delayed dry-run (certbot sleeps ~7.6min by design) ==="
sudo pkill -f "certbot renew" || true
sleep 1
pgrep -af certbot || echo "  no certbot process now"

echo
echo "=== re-run dry-run without the random sleep: does renewal actually work? ==="
sudo /opt/certbot/bin/certbot renew --dry-run --no-random-sleep-on-renew 2>&1 | tail -18

echo
echo "=== renewal config (records webroot + deploy hook path) ==="
sudo cat "/etc/letsencrypt/renewal/$IP.conf"

echo
echo "=== cron entry ==="
cat /etc/cron.d/certbot-renew
echo "=== DONE ==="
