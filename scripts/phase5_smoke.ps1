# ACP Copilot — Phase 5 冒烟测试
# 验证：短期记忆（同会话回忆）+ 长期记忆（跨会话画像召回）
$ErrorActionPreference = 'Stop'

$login = Invoke-RestMethod -Uri http://localhost:8080/api/auth/login -Method Post -ContentType 'application/json' -Body (@{username='testuser1';password='password123'} | ConvertTo-Json)
$h = @{ Authorization = "Bearer $($login.token)" }

$sb = New-Object System.Text.StringBuilder

function Turn([string]$user, [string]$session, [string]$msg) {
    $body = @{ user_id = $user; session_id = $session; message = $msg } | ConvertTo-Json
    $resp = Invoke-WebRequest -Uri http://localhost:8080/api/chat/memory -Method Post `
        -ContentType 'application/json; charset=utf-8' -Headers $h `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
    [void]$sb.AppendLine('### ' + $msg)
    [void]$sb.AppendLine($resp.Content)
    [void]$sb.AppendLine('')
}

Turn '1' 's1' '我叫小明，是零基础，准备两个月后考ACP云计算认证'
Turn '1' 's1' '我刚才说我叫什么名字？'
Turn '1' 's2' '我的学习基础怎么样？'

[System.IO.File]::WriteAllText('scripts\mem_out.txt', $sb.ToString(), [System.Text.Encoding]::UTF8)
Write-Output 'SAVED'
