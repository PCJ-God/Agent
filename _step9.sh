#!/usr/bin/env bash
set -uo pipefail
IP=139.155.146.41

echo "=== is a certbot run still going? ==="
pgrep -af certbot || echo "  no certbot process running"

echo
echo "=== why does http:// return 200 instead of 301? ==="
echo "--- full response headers for http://127.0.0.1/health ---"
curl -si http://127.0.0.1/health | head -12
echo "--- same request but with an explicit Host header ---"
curl -s -o /dev/null -w "  Host: $IP              -> %{http_code}\n" -H "Host: $IP" http://127.0.0.1/health
curl -s -o /dev/null -w "  Host: something.else   -> %{http_code}\n" -H "Host: something.else" http://127.0.0.1/health
echo "--- nginx config inventory ---"
ls -la /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>&1

echo
echo "=== certificate SAN (the IP must be in subjectAltName) ==="
sudo openssl x509 -in "/etc/letsencrypt/live/$IP/fullchain.pem" -noout -subject -dates -ext subjectAltName 2>&1

echo
echo "=== unit warnings since the LAST restart only ==="
SINCE=$(systemctl show agent -p ActiveEnterTimestamp --value)
echo "active since: $SINCE"
sudo journalctl -u agent --since "$SINCE" --no-pager 2>&1 | grep -i "unknown key" || echo "  none -> unit file is clean now"

echo
echo "=== letsencrypt log tail (dry-run outcome) ==="
sudo tail -14 /var/log/letsencrypt/letsencrypt.log 2>&1
echo "=== DONE ==="
