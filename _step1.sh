#!/usr/bin/env bash
# Step 1: service account + clone + venv + dependency resolution probe.
# Idempotent. ASCII only (avoids any encoding issue over scp/ssh).
set -euo pipefail

echo "=== 0) python3-venv available? ==="
if ! python3 -c "import venv" >/dev/null 2>&1; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv
fi
python3 --version

echo "=== 1) service account ==="
if id agent >/dev/null 2>&1; then
  echo "user 'agent' already exists"
else
  sudo useradd -r -m -d /home/agent -s /bin/bash agent
  echo "created user 'agent' (home /home/agent)"
fi
sudo mkdir -p /opt/agent
sudo chown agent:agent /opt/agent

echo "=== 2) clone branch multi-agent ==="
if [ -d /opt/agent/.git ]; then
  echo "already a git repo -> git pull"
  sudo -u agent git -C /opt/agent pull --ff-only
else
  if [ -n "$(ls -A /opt/agent)" ]; then
    echo "ERROR: /opt/agent is not empty and not a git repo"; exit 1
  fi
  sudo -u agent git clone -b multi-agent https://github.com/PCJ-God/Agent.git /opt/agent
fi
echo "--- repo contents ---"
ls /opt/agent
echo "--- sanity ---"
test -f /opt/agent/scripts/run_server.py && echo "run_server.py OK"
test -f /opt/agent/deploy/agent.service && echo "agent.service OK"

echo "=== 3) venv ==="
[ -x /opt/agent/.venv/bin/python ] || sudo -u agent python3 -m venv /opt/agent/.venv
/opt/agent/.venv/bin/python --version
sudo -u agent /opt/agent/.venv/bin/pip install -q -U pip
/opt/agent/.venv/bin/pip --version

echo "=== 4) dependency resolution probe (no install) ==="
sudo -u agent /opt/agent/.venv/bin/pip install --dry-run \
  -i https://mirrors.cloud.tencent.com/pypi/simple \
  --report /tmp/pip-report.json \
  -r /opt/agent/requirements.txt > /tmp/dryrun.log 2>&1 || {
    echo "!!! DRY-RUN FAILED -- last 40 lines:"; tail -40 /tmp/dryrun.log; exit 1; }

echo "DRY-RUN OK"
echo "--- versions that WOULD be installed (key packages) ---"
python3 - <<'PY'
import json
names = {"agentscope","dashscope","mem0ai","qdrant-client","pydantic","numpy",
         "grpcio","aiohttp","openai","fastapi","uvicorn"}
d = json.load(open("/tmp/pip-report.json"))
rows = []
for i in d.get("install", []):
    m = i["metadata"]
    if m["name"].lower() in names:
        rows.append((m["name"], m["version"]))
for n, v in sorted(rows, key=lambda x: x[0].lower()):
    print(f"{n}=={v}")
print("total packages:", len(d.get("install", [])))
PY

echo "=== 5) would anything need building from source? ==="
grep -iE "building wheel|Building wheel|from source|sdist" /tmp/dryrun.log | head -20 || echo "(none reported)"
echo "=== done ==="
