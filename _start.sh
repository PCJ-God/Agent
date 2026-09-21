#!/usr/bin/env bash
set -uo pipefail

echo "=== 1) 重启服务（字面意义的「启动」）==="
sudo systemctl restart agent
sleep 5
echo "  is-active: $(systemctl is-active agent)"
echo -n "  health   : "; curl -s http://127.0.0.1:8000/health; echo

echo
echo "=== 2) 注册用户拿 token ==="
REG=$(curl -s -X POST http://127.0.0.1:8000/api/auth/register \
      -H 'Content-Type: application/json' -d '{"name":"start-check"}')
TK=$(echo "$REG" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])' 2>/dev/null)
SID=$(python3 -c 'import uuid;print(uuid.uuid4())')
echo "  token 长度=${#TK}   session_id=$SID"

echo
echo "=== 3) 真实对话请求（真的会调 DashScope + agentscope + 记忆层）==="
echo "    最长等 180 秒 —— 这一步才能真正说明「跑起来了」"
curl -s --max-time 180 -X POST http://127.0.0.1:8000/api/chat \
  -H "Authorization: Bearer $TK" -H 'Content-Type: application/json' \
  -d "{\"message\":\"用一句话自我介绍，并说明你能帮学生做什么\",\"session_id\":\"$SID\"}" \
  -o /tmp/chat.json -w '  HTTP %{http_code}   耗时 %{time_total}s\n'
echo "  --- 响应内容（前 1500 字符）---"
head -c 1500 /tmp/chat.json 2>/dev/null; echo

echo
echo "=== 4) 这期间服务端日志 ==="
sudo journalctl -u agent --since "4 minutes ago" --no-pager | tail -30
echo "=== DONE ==="
