#!/usr/bin/env bash
set -euo pipefail

# GitHub is NOT reliably reachable from this server (GnuTLS recv error -110),
# so we do not rely on `git pull` here. The install-time constraints are written
# straight to /tmp; deliberately NOT into /opt/agent, because an untracked
# constraints.txt inside the repo would collide with a future `git pull`.
cat > /tmp/constraints.txt <<'EOF'
agentscope==1.0.18
openai==2.45.0
dashscope==1.27.6
mcp==1.29.0
mem0ai==1.0.11
qdrant-client==1.19.0
pydantic==2.12.3
aiohttp==3.14.3
PyYAML==6.0.3
python-dotenv==1.2.2
fastapi==0.136.3
uvicorn==0.49.0
rich==15.0.0
EOF
echo "constraints ready ($(grep -c '==' /tmp/constraints.txt) pinned entries)"

echo "=== INSTALL start: $(date '+%H:%M:%S') ==="
echo "    109 packages via Tencent mirror; full log -> /tmp/pip-install.log"
sudo -u agent /opt/agent/.venv/bin/pip install \
  -i https://mirrors.cloud.tencent.com/pypi/simple \
  -c /tmp/constraints.txt \
  -r /opt/agent/requirements.txt > /tmp/pip-install.log 2>&1 || {
    echo "!!! INSTALL FAILED -- last 30 lines of log:"; tail -30 /tmp/pip-install.log; exit 1; }
echo "=== INSTALL done: $(date '+%H:%M:%S') ==="
echo "--- pip log tail ---"
tail -6 /tmp/pip-install.log

echo "=== installed key versions (must match constraints) ==="
/opt/agent/.venv/bin/pip list 2>/dev/null \
  | grep -iE "^(agentscope|openai|dashscope|mem0ai|qdrant-client|pydantic|fastapi|uvicorn|mcp) " || true

echo "=== import the real dependency chain ==="
sudo -u agent bash -c "cd /opt/agent && ./.venv/bin/python -c 'import src.config, src.orchestration.hierarchical; print(\"IMPORT_CHAIN_OK\")'"

echo "=== ALL DONE: $(date '+%H:%M:%S') ==="
