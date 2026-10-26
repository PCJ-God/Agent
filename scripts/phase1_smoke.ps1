# ACP Copilot — Phase 1 冒烟测试
# 验证：gateway/ai-engine/nginx 三个 /health，以及注册 -> 登录 -> 带 JWT 查 /me 全链路
$ErrorActionPreference = 'Stop'

Write-Output '=== [1/6] gateway /health ==='
(Invoke-RestMethod http://localhost:8080/health) | ConvertTo-Json -Compress

Write-Output '=== [2/6] ai-engine /health ==='
(Invoke-RestMethod http://localhost:8000/health) | ConvertTo-Json -Compress

Write-Output '=== [3/6] nginx -> gateway /health ==='
(Invoke-RestMethod http://localhost:8081/health) | ConvertTo-Json -Compress

$body = @{ username = 'testuser1'; password = 'password123' } | ConvertTo-Json

Write-Output '=== [4/6] register ==='
$reg = Invoke-RestMethod -Uri http://localhost:8080/api/auth/register -Method Post -ContentType 'application/json' -Body $body
$reg | ConvertTo-Json -Compress

Write-Output '=== [5/6] login ==='
$login = Invoke-RestMethod -Uri http://localhost:8080/api/auth/login -Method Post -ContentType 'application/json' -Body $body
$login | ConvertTo-Json -Compress

Write-Output '=== [6/6] me (with JWT) ==='
$me = Invoke-RestMethod -Uri http://localhost:8080/api/auth/me -Method Get -Headers @{ Authorization = "Bearer $($login.token)" }
$me | ConvertTo-Json -Compress

Write-Output '=== PHASE-1 SMOKE OK ==='
