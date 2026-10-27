$ErrorActionPreference = 'SilentlyContinue'

function Test-Port {
    param([string]$ip, [int]$port, [int]$timeoutMs = 2000)
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $ar = $c.BeginConnect($ip, $port, $null, $null)
        $ok = $ar.AsyncWaitHandle.WaitOne($timeoutMs, $false)
        if ($ok -and $c.Connected) { return 'OPEN' }
        if (-not $ok) { return 'TIMEOUT' }
        return 'REFUSED'
    } catch {
        return 'ERR'
    } finally {
        $c.Close()
    }
}

Write-Output '=== TCP probe ==='
$targets = @(
    @('132.232.154.39', 80),
    @('132.232.154.39', 443),
    @('132.232.154.39', 8081),
    @('132.232.154.39', 8000),
    @('132.232.154.39', 3000),
    @('139.155.146.41', 80),
    @('139.155.146.41', 443),
    @('139.155.146.41', 8081)
)
foreach ($t in $targets) {
    $r = Test-Port $t[0] $t[1]
    Write-Output ("{0}:{1,-5} {2}" -f $t[0], $t[1], $r)
}

Write-Output ''
Write-Output '=== HTTP probe (curl) ==='
$urls = @(
    'http://lovekiki.site/',
    'https://lovekiki.site/',
    'http://132.232.154.39:8081/',
    'http://139.155.146.41/'
)
foreach ($u in $urls) {
    $out = curl.exe -s -k -o NUL -w '%{http_code} ip=%{remote_ip} time=%{time_total}' --max-time 8 $u 2>&1
    Write-Output ("{0,-34} {1}" -f $u, ($out -join ' '))
}

Write-Output ''
Write-Output '=== DNS resolve x5 (order varies = round-robin) ==='
for ($i = 1; $i -le 5; $i++) {
    $r = Resolve-DnsName -Name lovekiki.site -Type A -Server 119.29.29.29 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress } | ForEach-Object { $_.IPAddress }
    Write-Output ("try{0}: {1}" -f $i, ($r -join ', '))
}
