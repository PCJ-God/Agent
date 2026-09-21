#!/usr/bin/env bash
set -euo pipefail

echo "=== pull latest (need constraints.txt) ==="
sudo -u agent git -C /opt/agent pull --ff-only
test -f /opt/agent/constraints.txt && echo "constraints.txt OK"

echo "=== REAL INSTALL start: $(date '+%H:%M:%S') ==="
echo "    (109 packages, ~1.9 GB, via Tencent mirror; log -> /tmp/pip-install.log)"
sudo -u agent /opt/agent/.venv/bin/pip install \
  -i https://mirrors.cloud.tencent.com/pypi/simple \
  -c /opt/agent/constraints.txt \
  -r /opt/agent/requirements.txt > /tmp/pip-install.log 2>&1
echo "=== REAL INSTALL done: $(date '+%H:%M:%S') ==="
echo "--- last 12 lines of pip log ---"
tail -12 /tmp/pip-install.log

echo "=== installed versions (sanity) ==="
/opt/agent/.venv/bin/pip list 2>/dev/null | grep -iE "^(agentscope|openai|dashscope|mem0ai|qdrant-client|pydantic|fastapi|uvicorn|mcp) " || true

echo "=== import the real dependency chain ==="
sudo -u agent bash -c "cd /opt/agent && ./.venv/bin/python -c 'import src.config, src.orchestration.hierarchical; print(\"IMPORT_CHAIN_OK\")'"
echo "=== done: $(date '+%H:%M:%S') ==="
