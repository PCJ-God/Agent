#!/usr/bin/env bash
# 验证「手动前台启动」的确切命令，验证完把 systemd 交回。
set -uo pipefail

echo "=== 1) 先停掉 systemd 那个（否则 8000 被占）==="
sudo systemctl stop agent
sleep 3
if ss -ltn 2>/dev/null | grep -q ':8000'; then echo "  !! 8000 仍被占用"; else echo "  8000 已释放"; fi

echo
echo "=== 2) 用你将来要敲的那条命令前台启动（相对路径、agent 用户、项目目录）==="
echo "    cd /opt/agent"
echo "    sudo -u agent ./.venv/bin/python scripts/run_server.py"
cd /opt/agent || exit 1
sudo -u agent timeout 15 ./.venv/bin/python scripts/run_server.py > /tmp/manual_start.log 2>&1 &
MPID=$!
sleep 8

echo
echo "=== 3) 启动日志（你自己敲的时候看到的就是这些）==="
cat /tmp/manual_start.log

echo
echo "=== 4) 真的起来了吗 ==="
echo -n "  /health : "; curl -s -m 5 http://127.0.0.1:8000/health; echo
curl -s -m 5 -o /dev/null -w '  /       : %{http_code} %{content_type}\n' http://127.0.0.1:8000/
echo "  前台跑的时候网站照样能用吗（nginx 代理到 8000）:"
curl -sk -m 5 -o /dev/null -w '  https://127.0.0.1/health -> %{http_code}\n' https://127.0.0.1/health

echo
echo "=== 5) 收尾：等它超时退出，把 systemd 交回去 ==="
wait $MPID 2>/dev/null
sleep 2
sudo systemctl start agent
sleep 5
echo "  is-active: $(systemctl is-active agent)"
echo -n "  health   : "; curl -s -m 5 http://127.0.0.1:8000/health; echo
echo "=== DONE ==="
