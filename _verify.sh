#!/usr/bin/env bash
# Agent 部署自查脚本 —— 直接把 /opt/agent 的真实状态打出来。
# 用法: bash /opt/verify-agent.sh
set -uo pipefail
IP=139.155.146.41
APP=/opt/agent
# 让这个脚本在服务器上留一份，方便你自己反复跑
sudo cp "$0" /opt/verify-agent.sh 2>/dev/null && sudo chmod 755 /opt/verify-agent.sh 2>/dev/null

hr() { echo; echo "==================== $* ===================="; }

hr "1. 代码是否真的在磁盘上"
ls -la "$APP" | head -18
echo "--- 关键文件（大小不为 0 才算真在） ---"
for f in src/access/auth.py src/access/server.py src/access/ratelimit.py \
         src/storage/memory/session_store.py src/orchestration/hierarchical.py \
         scripts/run_server.py frontend/index.html requirements.txt constraints.txt \
         deploy/agent.service deploy/nginx.conf docs/DEPLOY.md; do
  if [ -f "$APP/$f" ]; then
    printf "  OK   %-42s %8s bytes\n" "$f" "$(stat -c%s "$APP/$f")"
  else
    printf "  MISS %-42s\n" "$f"
  fi
done

hr "2. Python 环境与包版本"
"$APP/.venv/bin/python" --version
"$APP/.venv/bin/pip" list 2>/dev/null | grep -iE "^(agentscope|openai|mem0ai|dashscope|qdrant-client|pydantic|fastapi|uvicorn|mcp) " | sed 's/^/  /'

hr "3. .env（key 已打码，永远不要贴原文）"
sudo ls -l "$APP/.env"
sudo sed -E 's/^(DASHSCOPE_API_KEY=).*/\1***masked***/' "$APP/.env" \
  | grep -E "^(DASHSCOPE_API_KEY|LLM_MODEL|HOST|PORT|FORWARDED_ALLOW_IPS|LTM_SCOPE)=" | sed 's/^/  /'

hr "4. systemd 服务"
echo "  is-active : $(systemctl is-active agent)"
echo "  is-enabled: $(systemctl is-enabled agent)"
echo "  started   : $(systemctl show agent -p ActiveEnterTimestamp --value)"
systemctl status agent --no-pager 2>&1 | head -6 | sed 's/^/  /'

hr "5. 应用真实响应（重点：根路径返回的是不是真 HTML）"
echo "--- GET /health ---"
curl -s http://127.0.0.1:8000/health; echo
echo "--- GET /  的 Content-Type 与字节数 ---"
curl -s -o /tmp/root.html -w '  content-type=%{content_type}  bytes=%{size_download}\n' http://127.0.0.1:8000/
echo "--- GET /  前 14 行 ---"
head -14 /tmp/root.html | sed 's/^/  | /'
echo "--- 页面上引用的静态资源是否真能取到 ---"
for a in $(grep -oE '/static/[a-zA-Z0-9_./-]+' /tmp/root.html 2>/dev/null | sort -u | head -5); do
  printf "  %-38s -> %s\n" "$a" "$(curl -s -o /dev/null -w '%{http_code} %{content_type}' "http://127.0.0.1:8000$a")"
done
rm -f /tmp/root.html

hr "6. 认证层是否真的在拦人"
curl -s -o /dev/null -w '  无 token   /api/sessions -> %{http_code}  (401 = 在拦)\n' http://127.0.0.1:8000/api/sessions
curl -s -X POST http://127.0.0.1:8000/api/auth/register -H 'Content-Type: application/json' \
  -d '{"name":"verify-check"}' -o /tmp/reg.json -w '  注册       /api/auth/register -> %{http_code}\n'
TK=$(python3 -c 'import json;print(json.load(open("/tmp/reg.json")).get("token",""))' 2>/dev/null)
echo "  拿到的 token 长度: ${#TK}"
curl -s -o /dev/null -w '  带 token   /api/auth/me -> %{http_code}  (200 = token 有效)\n' \
  http://127.0.0.1:8000/api/auth/me -H "Authorization: Bearer $TK"
rm -f /tmp/reg.json

hr "7. 端口暴露面（关键：8000 只能出现在 127.0.0.1，不能是 0.0.0.0）"
sudo ss -ltnp 2>/dev/null | grep -E ':(80|443|8000) ' | awk '{print "  "$4"   "$6}'

hr "8. nginx 与证书"
sudo nginx -t 2>&1 | sed 's/^/  /'
echo "  server_name: $(sudo grep -m1 'server_name' /etc/nginx/conf.d/agent.conf | tr -d ' ')"
sudo openssl x509 -in "/etc/letsencrypt/live/$IP/fullchain.pem" -noout -subject -dates -ext subjectAltName 2>&1 | sed 's/^/  /'
echo "  --- 本地走 nginx 的访问 ---"
curl -sk -o /dev/null -w '  https 127.0.0.1/health -> %{http_code}\n' https://127.0.0.1/health
curl -s  -o /dev/null -w '  http  127.0.0.1/health -> %{http_code}  (301 = 跳转正常)\n' http://127.0.0.1/health

hr "9. 续期"
cat /etc/cron.d/certbot-renew | sed 's/^/  /'

hr "10. 磁盘与内存"
df -h / | tail -1 | sed 's/^/  /'
free -m | head -2 | sed 's/^/  /'

echo
echo "==================== 自查结束 ===================="
