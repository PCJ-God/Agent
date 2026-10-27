$ErrorActionPreference = 'Stop'
$root = 'E:\github项目经历\大模型应用开发\Agent'

# 把字面目录 %TEMP% 重命名为 _scratch（PowerShell 误建）
$weird = Join-Path $root '%TEMP%'
if (Test-Path -LiteralPath $weird) {
    Rename-Item -LiteralPath $weird -NewName '_scratch'
    Write-Output "renamed %TEMP% -> _scratch"
}

$py = Join-Path $root '_scratch\asvenv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $py)) { throw "venv python not found: $py" }
& $py (Join-Path $root 'scripts\_introspect_as.py')
