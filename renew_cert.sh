#!/usr/bin/env bash
# Let's Encrypt 自动续期（webroot 模式，无需停 nginx）。建议每天由 cron 触发；未到期时 certbot 自行跳过。
set +e
cd "$HOME/acp" || exit 1
DOMAIN=lovekiki.site
BEFORE=$(sudo md5sum deploy/certs/server.crt | awk '{print $1}')

sudo docker run --rm \
  -v "$HOME/acp/deploy/letsencrypt:/etc/letsencrypt" \
  -v "$HOME/acp/deploy/certbot/www:/var/www/certbot" \
  certbot/certbot renew --webroot -w /var/www/certbot --quiet 2>&1

sudo cp -L "deploy/letsencrypt/live/$DOMAIN/fullchain.pem" deploy/certs/server.crt
sudo cp -L "deploy/letsencrypt/live/$DOMAIN/privkey.pem"  deploy/certs/server.key
sudo chmod 600 deploy/certs/server.key
AFTER=$(sudo md5sum deploy/certs/server.crt | awk '{print $1}')

if [ "$BEFORE" != "$AFTER" ]; then
  echo "$(date -Is) cert renewed -> restart nginx" >> "$HOME/acp/renew.log"
  sudo docker compose restart nginx
else
  echo "$(date -Is) no renewal needed" >> "$HOME/acp/renew.log"
fi
