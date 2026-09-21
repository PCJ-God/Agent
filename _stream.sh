#!/usr/bin/env bash
set -uo pipefail
IP=139.155.146.41

echo "=== 0) 服务端到底有没有在要客户端证书（解释 schannel 反复协商）==="
echo | openssl s_client -connect 127.0.0.1:443 -servername "$IP" 2>/dev/null \
  | grep -iE "Acceptable client certificate|Verify return code|Protocol *:|Cipher *:" | head -6 \
  || echo "  (取不到)"

echo
echo "=== 1) 注册一个用户 ==="
REG=$(curl -sk -X POST https://127.0.0.1/api/auth/register \
      -H 'Content-Type: application/json' -d '{"name":"stream-check"}')
TK=$(echo "$REG" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])' 2>/dev/null)
SID=$(python3 -c 'import uuid;print(uuid.uuid4())')
echo "  token 长度=${#TK}"

echo
echo "=== 2) 走 nginx 的流式请求：每个事件打上到达时间 ==="
echo "    （时间戳逐渐拉开 = 真流式；全部挤在最后一刻 = 被缓冲了）"
curl -skN --max-time 220 -X POST https://127.0.0.1/api/chat/stream \
  -H "Authorization: Bearer $TK" -H 'Content-Type: application/json' \
  -d "{\"message\":\"请分三点说明什么是递归，每点一句话\",\"session_id\":\"$SID\"}" \
  | python3 -u -c '
import sys, time
t0 = time.time()
n = 0
for line in sys.stdin:
    n += 1
    print(f"[+{time.time()-t0:7.2f}s] {line.rstrip()[:160]}")
print(f"--- 共 {n} 行, 总耗时 {time.time()-t0:.2f}s ---")
'

echo
echo "=== 3) nginx 侧是否真的把流透传了（看它自己的日志）==="
sudo tail -6 /var/log/nginx/access.log
echo "=== DONE ==="
