#!/usr/bin/env bash
# Foreground-equivalent smoke test. No `set -e`: we want every result printed.
set -uo pipefail

echo "=== start app as 'agent' user (nohup, log -> /tmp/app.log) ==="
sudo -u agent bash -c 'cd /opt/agent && nohup ./.venv/bin/python scripts/run_server.py > /tmp/app.log 2>&1 &'
sleep 4

echo "=== wait for /health (max 70s) ==="
READY=no
for i in $(seq 1 35); do
  C=$(curl -s -o /tmp/health.json -w '%{http_code}' http://127.0.0.1:8000/health 2>/dev/null || echo 000)
  if [ "$C" = "200" ]; then READY=yes; echo "ready after ~$((i*2))s"; break; fi
  if ! pgrep -u agent -f run_server.py >/dev/null 2>&1; then echo "!! process died before becoming healthy"; break; fi
  sleep 2
done

if [ "$READY" != "yes" ]; then
  echo "!!! DID NOT BECOME HEALTHY -- last 45 lines of /tmp/app.log:"
  tail -45 /tmp/app.log
  sudo pkill -u agent -f run_server.py || true
  exit 1
fi

echo "--- GET /health ---"
cat /tmp/health.json; echo

echo "--- unauthenticated GET /api/sessions (expect 401) ---"
curl -s -o /dev/null -w '  status=%{http_code}\n' http://127.0.0.1:8000/api/sessions

echo "--- POST /api/auth/register ---"
REG=$(curl -s -X POST http://127.0.0.1:8000/api/auth/register \
      -H 'Content-Type: application/json' -d '{"name":"smoke-test"}')
echo "  body: $(echo "$REG" | head -c 220)"
TOKEN=$(echo "$REG" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))' 2>/dev/null)

if [ -n "$TOKEN" ]; then
  echo "--- GET /api/auth/me with token (expect 200) ---"
  curl -s -o /dev/null -w '  status=%{http_code}\n' http://127.0.0.1:8000/api/auth/me \
    -H "Authorization: Bearer $TOKEN"
  echo "--- GET /api/sessions with token (expect 200) ---"
  curl -s -o /dev/null -w '  status=%{http_code}\n' http://127.0.0.1:8000/api/sessions \
    -H "Authorization: Bearer $TOKEN"
else
  echo "!!! register returned no token"
fi

echo "=== app log tail ==="
tail -25 /tmp/app.log

echo "=== stop app ==="
sudo pkill -u agent -f run_server.py || true
sleep 3
if ss -ltn 2>/dev/null | grep -q ':8000'; then echo "!! STILL LISTENING on 8000"; else echo "port 8000 released"; fi
echo "=== DONE ==="
