# ACP Copilot — Phase 3 冒烟测试
# 验证：登录 -> 摄入知识库文档 -> RAG 检索增强对话（先回传引用来源，再流式生成）
$ErrorActionPreference = 'Stop'

$login = Invoke-RestMethod -Uri http://localhost:8080/api/auth/login -Method Post -ContentType 'application/json' -Body (@{username='testuser1';password='password123'} | ConvertTo-Json)
$h = @{ Authorization = "Bearer $($login.token)" }

Write-Output '=== [1/2] /api/rag/ingest ==='
$ing = Invoke-RestMethod -Uri http://localhost:8080/api/rag/ingest -Method Post -ContentType 'application/json' -Headers $h -Body '{}'
$ing | ConvertTo-Json -Compress

$q = @{ query = 'OSS 有哪些存储类型，各自适合什么场景' } | ConvertTo-Json
Write-Output '=== [2/2] /api/chat/rag ==='
$resp = Invoke-WebRequest -Uri http://localhost:8080/api/chat/rag -Method Post `
    -ContentType 'application/json; charset=utf-8' -Headers $h `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($q))
Write-Output $resp.Content
Write-Output '=== PHASE-3 SMOKE OK ==='
