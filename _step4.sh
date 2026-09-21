#!/usr/bin/env bash
set -euo pipefail

echo "=== retry git pull (GitHub is intermittent from this host; non-fatal) ==="
if sudo -u agent git -C /opt/agent pull --ff-only 2>&1; then
  echo "pull OK -> HEAD now $(sudo -u agent git -C /opt/agent rev-parse --short HEAD)"
else
  echo "pull FAILED again -- staying at $(sudo -u agent git -C /opt/agent rev-parse --short HEAD)"
  echo "(this only means the repo lacks constraints.txt; the install already used /tmp/constraints.txt)"
fi

echo "=== .env ==="
if [ -f /opt/agent/.env ]; then
  echo ".env already exists -> leaving contents alone"
else
  sudo -u agent cp /opt/agent/.env.example /opt/agent/.env
  echo "created /opt/agent/.env from .env.example"
fi
sudo chown agent:agent /opt/agent/.env
sudo chmod 600 /opt/agent/.env

echo "--- effective settings (API key value masked) ---"
sudo -u agent grep -E "^(DASHSCOPE_API_KEY|LLM_MODEL|HOST|PORT|FORWARDED_ALLOW_IPS|QDRANT_URL|MAX_SESSIONS_PER_USER|MAX_TEAMS|RATE_LIMIT_PER_MINUTE|LTM_SCOPE|ENABLE_LONG_TERM_MEMORY)=" /opt/agent/.env \
  | sed -E 's/^(DASHSCOPE_API_KEY=).*/\1<value hidden>/'

echo "=== skills on server ==="
find /opt/agent/skills -name SKILL.md 2>/dev/null | sed 's|/opt/agent/||' || echo "(none)"

echo "=== auth / session files present? ==="
for f in src/access/auth.py src/storage/memory/session_store.py deploy/agent.service; do
  if [ -f "/opt/agent/$f" ]; then echo "OK   $f"; else echo "MISS $f"; fi
done

echo "=== is anything already listening on 8000? ==="
(ss -ltnp 2>/dev/null | grep ':8000' || echo "port 8000 free")

echo "=== DONE ==="
