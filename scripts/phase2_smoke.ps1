# ACP Copilot — Phase 2 冒烟测试
# 验证：登录 -> POST /api/chat（JWT）-> SSE 流式返回通义千问回答
$ErrorActionPreference = 'Stop'

$loginBody = @{ username = 'testuser1'; password = 'password123' } | ConvertTo-Json
$login = Invoke-RestMethod -Uri http://localhost:8080/api/auth/login -Method Post -ContentType 'application/json' -Body $loginBody
Write-Output ('LOGIN OK, uid=' + $login.user.id)

$chatBody = @{ messages = @(@{ role = 'user'; content = '用一句话解释什么是弹性伸缩（Auto Scaling）' }) } | ConvertTo-Json

Write-Output '=== /api/chat 流式输出 ==='
$resp = Invoke-WebRequest -Uri http://localhost:8080/api/chat -Method Post `
    -ContentType 'application/json; charset=utf-8' `
    -Headers @{ Authorization = "Bearer $($login.token)" } `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($chatBody))
Write-Output $resp.Content
Write-Output '=== PHASE-2 SMOKE OK ==='
