#Requires -Version 5.1

<#
.SYNOPSIS
  Quoroom - start the whole local stand with one command.

.DESCRIPTION
  Starts the Docker infrastructure (Continuwuity, Element, Caddy) and the
  session broker.

  This is NOT the first-time setup. Certificates, accounts and
  bridge/config.yaml are made once, following docs/INSTALL.md; this script only
  starts a stand that is already set up. It is idempotent: a second call does
  not start a second broker.

  The messages are printed in the room language: --lang en|ru if given,
  otherwise the language key of bridge/config.yaml, otherwise English. Any
  other value gives English.

.PARAMETER Logs
  Start, then follow the broker log (Ctrl+C exits, the stand stays up).

.EXAMPLE
  .\start.ps1

.EXAMPLE
  .\start.ps1 -Logs

.EXAMPLE
  .\start.ps1 --lang ru
#>
param(
    [switch]$Logs
)

$ErrorActionPreference = 'Stop'

$root       = $PSScriptRoot
$dockerDir  = Join-Path $root 'docker'
$bridgeDir  = Join-Path $root 'bridge'
$python     = Join-Path $bridgeDir '.venv\Scripts\python.exe'
$config     = Join-Path $bridgeDir 'config.yaml'
$logFile    = Join-Path $bridgeDir 'broker.log'
$pidFile    = Join-Path $bridgeDir 'state\broker.pid'
$brokerPort = 8770

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
    $errorLabel = 'ОШИБКА'
    $warningLabel = 'ПРЕДУПРЕЖДЕНИЕ'
    $texts = @{
        docker_missing  = 'docker не найден в PATH. Установите Docker Desktop (docs/INSTALL.md, шаг 0).'
        docker_down     = 'Docker-демон не отвечает. Запустите Docker Desktop и повторите.'
        no_env          = 'нет docker/.env - скопируйте docker/.env.example -> docker/.env (docs/INSTALL.md, шаг 3).'
        no_venv         = 'нет окружения bridge/.venv - создайте его (docs/INSTALL.md, шаг 5).'
        no_config       = 'нет bridge/config.yaml - скопируйте config.example.yaml и впишите токены (docs/INSTALL.md, шаг 7).'
        stack_up        = '==> Поднимаю Docker-стек (Continuwuity, Element, Caddy)...'
        compose_failed  = 'docker compose up завершился с ошибкой.'
        waiting         = '==> Жду готовности Matrix-сервера (порт 443)...'
        port_443        = '443 не отвечает за 60с. Проверьте: docker compose -f docker/docker-compose.yml logs continuwuity'
        already_running = '==> Брокер уже работает (PID {0}) - второй не запускаю.'
        port_busy       = 'порт {0} занят, но pid-файла нет - его держит чужой процесс. Остановите прежний брокер и повторите.'
        starting        = '==> Запускаю брокер (лог: bridge/broker.log)...'
        exited          = "брокер завершился при старте. Из лога:`n  {0}`n(полный лог: bridge/broker.log)"
        ready           = '==> Брокер готов (PID {0}, порт {1}).'
        no_port         = 'брокер не открыл порт {0} за 10с. Смотрите bridge/broker.log.'
        done            = 'Готово. Element Web: https://agentschat.local'
        next            = 'Дальше в каждой сессии CLI вызвать /chatlogin. Остановить всё: .\stop.ps1'
        follow          = '==> Лог брокера (Ctrl+C - выйти, стенд останется поднятым):'
    }
} else {
    $errorLabel = 'ERROR'
    $warningLabel = 'WARNING'
    $texts = @{
        docker_missing  = 'docker was not found in PATH. Install Docker Desktop (docs/INSTALL.md, step 0).'
        docker_down     = 'The Docker daemon is not responding. Start Docker Desktop and run this again.'
        no_env          = 'docker/.env is missing - copy docker/.env.example to docker/.env (docs/INSTALL.md, step 3).'
        no_venv         = 'bridge/.venv is missing - create it (docs/INSTALL.md, step 5).'
        no_config       = 'bridge/config.yaml is missing - copy config.example.yaml and fill in the tokens (docs/INSTALL.md, step 7).'
        stack_up        = '==> Starting the Docker stack (Continuwuity, Element, Caddy)...'
        compose_failed  = 'docker compose up failed.'
        waiting         = '==> Waiting for the Matrix server (port 443)...'
        port_443        = 'port 443 did not answer within 60s. Check: docker compose -f docker/docker-compose.yml logs continuwuity'
        already_running = '==> The broker is already running (PID {0}) - not starting a second one.'
        port_busy       = 'port {0} is in use but there is no pid file - another process holds it. Stop the old broker and run this again.'
        starting        = '==> Starting the broker (log: bridge/broker.log)...'
        exited          = "the broker exited at startup. From the log:`n  {0}`n(full log: bridge/broker.log)"
        ready           = '==> The broker is ready (PID {0}, port {1}).'
        no_port         = 'the broker did not open port {0} within 10s. See bridge/broker.log.'
        done            = 'Done. Element Web: https://agentschat.local'
        next            = 'Next, call /chatlogin in each CLI session. To stop everything: .\stop.ps1'
        follow          = '==> Broker log (Ctrl+C to exit, the stack stays up):'
    }
}

function Text($key, $values) { $texts[$key] -f @($values) }
function Die($key, $values) { Write-Host "${errorLabel}: $(Text $key $values)" -ForegroundColor Red; exit 1 }
function Warn($key, $values) { Write-Host "${warningLabel}: $(Text $key $values)" -ForegroundColor Yellow }
function Say($key, $values) { Write-Host (Text $key $values) -ForegroundColor Cyan }

function Test-Port([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', $port); return $true }
    catch { return $false }
    finally { $client.Close() }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Die 'docker_missing' @()
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Die 'docker_down' @()
}
if (-not (Test-Path (Join-Path $dockerDir '.env'))) {
    Die 'no_env' @()
}
if (-not (Test-Path $python)) {
    Die 'no_venv' @()
}
if (-not (Test-Path $config)) {
    Die 'no_config' @()
}

Say 'stack_up' @()
Push-Location $dockerDir
try {
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { Die 'compose_failed' @() }
} finally { Pop-Location }

Say 'waiting' @()
$ready = $false
foreach ($i in 1..30) { if (Test-Port 443) { $ready = $true; break }; Start-Sleep -Seconds 2 }
if (-not $ready) {
    Warn 'port_443' @()
}

$running = $false
if (Test-Path $pidFile) {
    $existing = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($existing) { $existing = $existing.Trim() }
    $broker = $null
    if ($existing -match '^\d+$') {
        $broker = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$existing)" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match 'sessionchat\.broker' }
    }
    if ($broker) {
        $running = $true
        Say 'already_running' @($existing)
    } else {
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }
}

if (-not $running) {
    if (Test-Port $brokerPort) {
        Die 'port_busy' @($brokerPort)
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $pidFile) | Out-Null
    Say 'starting' @()
    $proc = Start-Process -FilePath $python `
        -ArgumentList '-X','utf8','-m','sessionchat.broker','--config','config.yaml','--verbose' `
        -WorkingDirectory $bridgeDir `
        -RedirectStandardError $logFile `
        -WindowStyle Hidden -PassThru
    $proc.Id | Out-File -FilePath $pidFile -Encoding ascii

    $up = $false
    foreach ($i in 1..10) {
        if ($proc.HasExited) {
            $lastLine = ''
            if (Test-Path $logFile) { $lastLine = (Get-Content $logFile -Tail 1 -ErrorAction SilentlyContinue) }
            Die 'exited' @($lastLine)
        }
        if (Test-Port $brokerPort) { $up = $true; break }
        Start-Sleep -Seconds 1
    }
    if ($up) { Say 'ready' @($proc.Id, $brokerPort) }
    else { Warn 'no_port' @($brokerPort) }
}

Write-Host ""
Write-Host (Text 'done' @()) -ForegroundColor Green
Write-Host (Text 'next' @()) -ForegroundColor Green

if ($Logs) {
    Say 'follow' @()
    Get-Content $logFile -Wait -Tail 20
}
