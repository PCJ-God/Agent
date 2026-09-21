#!/usr/bin/env bash
set -uo pipefail
IP=139.155.146.41

echo "=== 8a) is the unit warning actually gone since the restart? ==="
echo "active since: $(systemctl show agent -p ActiveEnterTimestamp --value)"
W=$(sudo journalctl -u agent --since "4 minutes ago" --no-pager | grep -ci "unknown key" || true)
echo "unknown-key warnings since restart: $W   (0 = genuinely clean)"

echo
echo "=== 8b) install the real HTTPS nginx config (repo copy still says agent.example.com) ==="
sudo sed "s/agent\.example\.com/$IP/g" /opt/agent/deploy/nginx.conf \
  | sudo tee /etc/nginx/conf.d/agent.conf >/dev/null
echo "--- server_name / cert paths after substitution ---"
grep -nE "server_name|ssl_certificate" /etc/nginx/conf.d/agent.conf

sudo nginx -t && sudo systemctl reload nginx
echo "reload rc=$?"

echo
echo "=== 8c) local probes through nginx ==="
curl -sk -o /dev/null -w 'https /health        -> %{http_code}\n' https://127.0.0.1/health
curl -s  -o /dev/null -w 'http  /health        -> %{http_code}  (expect 301)\n' http://127.0.0.1/health
curl -sk -o /dev/null -w 'https /api/sessions  -> %{http_code}  (expect 401)\n' https://127.0.0.1/api/sessions

echo
echo "=== 8d) inspect the certificate actually served on 443 ==="
echo | openssl s_client -connect 127.0.0.1:443 -servername "$IP" 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates 2>/dev/null || echo "(openssl probe failed)"

echo
echo "=== 8e) renewal must work: a 6-day cert that fails to renew = HTTPS dies in 6 days ==="
ls /etc/letsencrypt/renewal/ 2>&1
echo '0 3,15 * * * root /opt/certbot/bin/certbot renew --quiet --deploy-hook "systemctl reload nginx"' \
  | sudo tee /etc/cron.d/certbot-renew >/dev/null
sudo chmod 644 /etc/cron.d/certbot-renew
echo "--- installed cron ---"; cat /etc/cron.d/certbot-renew
echo "--- dry-run renewal (real validation against LE staging) ---"
sudo /opt/certbot/bin/certbot renew --dry-run 2>&1 | tail -14
echo "=== DONE ==="
