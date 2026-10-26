# ACP Copilot — Phase 4 冒烟测试
# 验证：Agent ReAct 循环 + 工具调用（本地 RAG 检索 / 联网搜索兜底）
$ErrorActionPreference = 'Stop'

$login = Invoke-RestMethod -Uri http://localhost:8080/api/auth/login -Method Post -ContentType 'application/json' -Body (@{username='testuser1';password='password123'} | ConvertTo-Json)
$h = @{ Authorization = "Bearer $($login.token)" }

function Test-Agent([string]$query) {
    Write-Output ("=== query: " + $query + " ===")
    $q = @{ query = $query } | ConvertTo-Json
    $resp = Invoke-WebRequest -Uri http://localhost:8080/api/chat/agent -Method Post `
        -ContentType 'application/json; charset=utf-8' -Headers $h `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($q))
    Write-Output $resp.Content
}

Test-Agent 'ECS 的安全组有什么作用？'
Test-Agent '阿里云2026年最新发布的大模型是什么？'
Write-Output '=== PHASE-4 SMOKE OK ==='
