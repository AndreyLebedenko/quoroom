#Requires -Version 5.1
<#
  Quoroom - остановить весь локальный стенд: брокер и Docker-инфраструктуру.

  Именованные Docker-тома (база Continuwuity, данные Caddy) сохраняются -
  данные не теряются, следующий .\start.ps1 поднимет всё как было.

    .\stop.ps1               # остановить брокер и опустить контейнеры
    .\stop.ps1 -KeepDocker   # остановить только брокер, контейнеры оставить
#>
[CmdletBinding()]
param(
    [switch]$KeepDocker
)

$ErrorActionPreference = 'Stop'

$root      = $PSScriptRoot
$dockerDir = Join-Path $root 'docker'
$bridgeDir = Join-Path $root 'bridge'
$pidFile   = Join-Path $bridgeDir 'state\broker.pid'

function Say($text) { Write-Host $text -ForegroundColor Cyan }

# --- 1. Брокер ---------------------------------------------------------
$stopped = $false
if (Test-Path $pidFile) {
    $bpid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($bpid) { $bpid = $bpid.Trim() }
    if ($bpid -and (Get-Process -Id ([int]$bpid) -ErrorAction SilentlyContinue)) {
        Say "==> Останавливаю брокер (PID $bpid)..."
        Stop-Process -Id ([int]$bpid) -Force
        $stopped = $true
    }
    Remove-Item $pidFile -ErrorAction SilentlyContinue
}

# Подстраховка: pid-файл потерян - ищем брокер по командной строке.
if (-not $stopped) {
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'sessionchat\.broker' }
    foreach ($p in $procs) {
        Say "==> Останавливаю брокер (PID $($p.ProcessId), найден по командной строке)..."
        Stop-Process -Id $p.ProcessId -Force
        $stopped = $true
    }
}
if (-not $stopped) { Say "==> Брокер не запущен." }

# --- 2. Docker ---------------------------------------------------------
if ($KeepDocker) {
    Say "==> Docker-контейнеры оставлены поднятыми (-KeepDocker)."
} elseif (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "ПРЕДУПРЕЖДЕНИЕ: docker не найден - контейнеры не тронуты." -ForegroundColor Yellow
} else {
    Say "==> Опускаю Docker-стек (тома с данными сохраняются)..."
    Push-Location $dockerDir
    try {
        docker compose down
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ПРЕДУПРЕЖДЕНИЕ: docker compose down вернул код $LASTEXITCODE (возможно, демон не запущен)." -ForegroundColor Yellow
        }
    } finally { Pop-Location }
}

Write-Host "Готово." -ForegroundColor Green
