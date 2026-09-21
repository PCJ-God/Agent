#!/usr/bin/env bash
set -euo pipefail

# Pinned to the versions verified in the local dev environment (Python 3.10.20).
# requirements.txt uses loose lower bounds (agentscope>=0.1.0 etc.), so a plain
# install resolves to agentscope 2.x / openai 3.x / mem0ai 2.x -- untested majors.
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

echo "=== pull latest (constraints may have been pushed) ==="
sudo -u agent git -C /opt/agent pull --ff-only || true

echo "=== dry-run WITH constraints, on Python $(/opt/agent/.venv/bin/python -V 2>&1) ==="
sudo -u agent /opt/agent/.venv/bin/pip install --dry-run \
  -i https://mirrors.cloud.tencent.com/pypi/simple \
  -c /tmp/constraints.txt \
  --report /tmp/pip-report2.json \
  -r /opt/agent/requirements.txt > /tmp/dryrun2.log 2>&1 || {
    echo "!!! DRY-RUN FAILED -- last 40 lines:"; tail -40 /tmp/dryrun2.log; exit 1; }

echo "DRY-RUN OK"
echo "--- resolved vs tested ---"
python3 - <<'PY'
import json
tested = {
    "agentscope": "1.0.18", "openai": "2.45.0", "dashscope": "1.27.6",
    "mcp": "1.29.0", "mem0ai": "1.0.11", "qdrant-client": "1.19.0",
    "pydantic": "2.12.3", "aiohttp": "3.14.3", "pyyaml": "6.0.3",
    "python-dotenv": "1.2.2", "fastapi": "0.136.3", "uvicorn": "0.49.0",
    "rich": "15.0.0",
}
d = json.load(open("/tmp/pip-report2.json"))
got = {}
for i in d.get("install", []):
    m = i["metadata"]
    got[m["name"].lower()] = m["version"]
for name, want in sorted(tested.items()):
    have = got.get(name, "(absent)")
    print(f"{'OK ' if have == want else 'DIFF'} {name:15s} tested={want:10s} resolved={have}")
print("total packages:", len(d.get("install", [])))
PY

echo "=== anything built from source? ==="
grep -iE "building wheel|from source|sdist" /tmp/dryrun2.log | head -20 || echo "(none reported)"
echo "=== done ==="
