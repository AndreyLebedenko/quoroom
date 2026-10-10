#Requires -Version 5.1

<#
.SYNOPSIS
  Quoroom - stop the whole local stand: the broker and the Docker infrastructure.

.DESCRIPTION
  The named Docker volumes (the Continuwuity database, the Caddy data) are
  kept, so no data is lost and the next .\start.ps1 brings everything back as
  it was.

  The messages are printed in the room language: --lang en|ru if given,
  otherwise the language key of bridge/config.yaml, otherwise English. Any
  other value gives English.

.PARAMETER KeepDocker
  Stop only the broker and leave the containers running.

.EXAMPLE
  .\stop.ps1

.EXAMPLE
  .\stop.ps1 -KeepDocker

.EXAMPLE
  .\stop.ps1 --lang ru
#>
param(
    [switch]$KeepDocker
)

$ErrorActionPreference = 'Stop'

$root      = $PSScriptRoot
$dockerDir = Join-Path $root 'docker'
$bridgeDir = Join-Path $root 'bridge'
$config    = Join-Path $bridgeDir 'config.yaml'
$pidFile   = Join-Path $bridgeDir 'state\broker.pid'

$language = $null
for ($position = 0; $position -lt $args.Count; $position++) {
    $argument = "$($args[$position])"
    if ($argument -ceq '--lang') {
        $language = ''
        if ($position + 1 -lt $args.Count) { $language = "$($args[$position + 1])" }
    } elseif ($argument.StartsWith('--lang=', [System.StringComparison]::Ordinal)) {
        $language = $argument.Substring('--lang='.Length)
    }
}
if ($null -eq $language -and (Test-Path -LiteralPath $config)) {
    $line = Select-String -LiteralPath $config -Pattern '^language:' -Encoding UTF8 |
        Select-Object -First 1
    if ($line) {
        $language = ($line.Line.Substring('language:'.Length) -replace '\s+#.*$', '').Trim()
        if ($language -match '^(["''])(.*)\1$') { $language = $Matches[2] }
    }
}

if ($language -ceq 'ru') {
    $warningLabel = 'ПРЕДУПРЕЖДЕНИЕ'
    $texts = @{
        stopping_broker = '==> Останавливаю брокер (PID {0})...'
        stopping_found  = '==> Останавливаю брокер (PID {0}, найден по командной строке)...'
        not_running     = '==> Брокер не запущен.'
        docker_kept     = '==> Docker-контейнеры оставлены поднятыми (-KeepDocker).'
        no_docker       = 'docker не найден - контейнеры не тронуты.'
        stopping_docker = '==> Опускаю Docker-стек (тома с данными сохраняются)...'
        down_failed     = 'docker compose down вернул код {0} (возможно, демон не запущен).'
        done            = 'Готово.'
    }
} else {
    $warningLabel = 'WARNING'
    $texts = @{
        stopping_broker = '==> Stopping the broker (PID {0})...'
        stopping_found  = '==> Stopping the broker (PID {0}, found by its command line)...'
        not_running     = '==> The broker is not running.'
        docker_kept     = '==> The Docker containers are left running (-KeepDocker).'
        no_docker       = 'docker was not found - the containers were not touched.'
        stopping_docker = '==> Bringing the Docker stack down (the data volumes are kept)...'
        down_failed     = 'docker compose down returned code {0} (the daemon may not be running).'
        done            = 'Done.'
    }
}

function Text($key, $values) { $texts[$key] -f @($values) }
function Warn($key, $values) { Write-Host "${warningLabel}: $(Text $key $values)" -ForegroundColor Yellow }
function Say($key, $values) { Write-Host (Text $key $values) -ForegroundColor Cyan }

$stopped = $false
if (Test-Path $pidFile) {
    $bpid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($bpid) { $bpid = $bpid.Trim() }
    $broker = $null
    if ($bpid -match '^\d+$') {
        $broker = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$bpid)" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match 'sessionchat\.broker' }
    }
    if ($broker) {
        Say 'stopping_broker' @($bpid)
        Stop-Process -Id $broker.ProcessId -Force
        $stopped = $true
    }
    Remove-Item $pidFile -ErrorAction SilentlyContinue
}

if (-not $stopped) {
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'sessionchat\.broker' }
    foreach ($p in $procs) {
        Say 'stopping_found' @($p.ProcessId)
        Stop-Process -Id $p.ProcessId -Force
        $stopped = $true
    }
}
if (-not $stopped) { Say 'not_running' @() }

if ($KeepDocker) {
    Say 'docker_kept' @()
} elseif (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Warn 'no_docker' @()
} else {
    Say 'stopping_docker' @()
    Push-Location $dockerDir
    try {
        docker compose down
        if ($LASTEXITCODE -ne 0) {
            Warn 'down_failed' @($LASTEXITCODE)
        }
    } finally { Pop-Location }
}

Write-Host (Text 'done' @()) -ForegroundColor Green
