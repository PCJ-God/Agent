# ACP Copilot — Phase 6 冒烟测试
# 验证：上传文档 -> MinIO 存储 + RabbitMQ 异步解析 -> worker 摄入 Chroma -> RAG 可检索到
$ErrorActionPreference = 'Stop'

$login = Invoke-RestMethod -Uri http://localhost:8080/api/auth/login -Method Post -ContentType 'application/json' -Body (@{username='testuser1';password='password123'} | ConvertTo-Json)
$h = @{ Authorization = "Bearer $($login.token)" }

Write-Output '=== [1/3] 上传 VPC 文档 ==='
$form = @{ file = Get-Item 'scripts\test_vpc.md' }
$up = Invoke-RestMethod -Uri http://localhost:8080/api/files/upload -Method Post -Headers $h -Form $form
Write-Output ($up | ConvertTo-Json -Compress)

Write-Output '=== [2/3] 等待 worker 异步解析（10s） ==='
Start-Sleep -Seconds 10

$q = @{ query = '什么是专有网络 VPC' } | ConvertTo-Json
Write-Output '=== [3/3] RAG 查询新上传的文档 ==='
$resp = Invoke-WebRequest -Uri http://localhost:8080/api/chat/rag -Method Post `
    -ContentType 'application/json; charset=utf-8' -Headers $h `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($q))
[System.IO.File]::WriteAllText('scripts\phase6_out.txt', $resp.Content, [System.Text.Encoding]::UTF8)
Write-Output '=== PHASE-6 SMOKE OK ==='
