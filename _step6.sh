#!/usr/bin/env bash
set -uo pipefail

echo "=== install systemd unit ==="
sudo cp /opt/agent/deploy/agent.service /etc/systemd/system/agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now agent
sleep 5

echo "=== unit file (check paths) ==="
grep -E "^(User|Group|WorkingDirectory|ExecStart|Restart|EnvironmentFile)" /etc/systemd/system/agent.service

echo "=== enabled / active ? ==="
echo "enabled: $(systemctl is-enabled agent 2>&1)"
echo "active : $(systemctl is-active agent 2>&1)"

echo "=== wait for /health via the service (max 40s) ==="
for i in $(seq 1 20); do
  C=$(curl -s -o /tmp/h.json -w '%{http_code}' http://127.0.0.1:8000/health 2>/dev/null || echo 000)
  if [ "$C" = "200" ]; then echo "healthy after ~$((i*2))s: $(cat /tmp/h.json)"; break; fi
  sleep 2
done

echo "=== systemctl status (head) ==="
systemctl status agent --no-pager 2>&1 | head -12

echo "=== journal tail ==="
sudo journalctl -u agent -n 12 --no-pager 2>&1 | tail -12

echo "=== will it come back after reboot? ==="
systemctl is-enabled agent
echo "=== DONE ==="
