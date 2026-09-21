#!/usr/bin/env bash
set -uo pipefail
F=/opt/agent/frontend

echo "=== frontend 目录内容 ==="
ls -la "$F"

echo
echo "=== index.html 里所有 src/href 引用 ==="
grep -oE '(src|href)="[^"]+"' "$F/index.html" | sort -u

echo
echo "=== 是否硬编码了 API 地址（关键：写死 127.0.0.1 的话，走 nginx 的浏览器会调崩）==="
grep -nE "http://127|https://127|localhost|:8000|API_BASE|BASE_URL" "$F/index.html" | head -20 \
  || echo "  （没有硬编码的 127.0.0.1 / localhost / :8000）"

echo
echo "=== 页面是怎么调后端的（fetch/EventSource 的用法）==="
grep -nE "fetch\(|EventSource\(|axios" "$F/index.html" | head -20

echo
echo "=== /static/ 这个挂载点到底有没有东西 ==="
curl -s -o /dev/null -w '  GET /static/          -> %{http_code}\n' http://127.0.0.1:8000/static/
curl -s -o /dev/null -w '  GET /static/index.html -> %{http_code}\n' http://127.0.0.1:8000/static/index.html
echo "=== 应用是否把其它路径也交给 nginx 之外的东西 ==="
curl -s -o /dev/null -w '  GET /app.js  -> %{http_code}\n' http://127.0.0.1:8000/app.js
echo "=== DONE ==="
