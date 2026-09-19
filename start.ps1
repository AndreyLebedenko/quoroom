#Requires -Version 5.1
<#
  Quoroom - поднять весь локальный стенд одной командой:
  Docker-инфраструктуру (Continuwuity, Element, Caddy) и брокер сессий.

  Это НЕ первичная настройка. Сертификаты, аккаунты и bridge/config.yaml
  делаются один раз по docs/INSTALL.md; здесь только запуск уже готового
  стенда. Скрипт идемпотентен: повторный вызов не поднимает второй брокер.

    .\start.ps1          # поднять всё
    .\start.ps1 -Logs    # поднять и показывать лог брокера (Ctrl+C - выйти,
                         #   стенд останется поднятым)
#>
[CmdletBinding()]
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

function Die($text) { Write-Host "ОШИБКА: $text" -ForegroundColor Red; exit 1 }
function Say($text) { Write-Host $text -ForegroundColor Cyan }

function Test-Port([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', $port); return $true }
    catch { return $false }
    finally { $client.Close() }
}

# --- Проверки окружения ------------------------------------------------
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Die "docker не найден в PATH. Установите Docker Desktop (docs/INSTALL.md, шаг 0)."
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Die "Docker-демон не отвечает. Запустите Docker Desktop и повторите."
}
if (-not (Test-Path (Join-Path $dockerDir '.env'))) {
    Die "нет docker/.env - скопируйте docker/.env.example -> docker/.env (docs/INSTALL.md, шаг 3)."
}
if (-not (Test-Path $python)) {
    Die "нет окружения bridge/.venv - создайте его (docs/INSTALL.md, шаг 5)."
}
if (-not (Test-Path $config)) {
    Die "нет bridge/config.yaml - скопируйте config.example.yaml и впишите токены (docs/INSTALL.md, шаг 7)."
}

# --- 1. Docker-инфраструктура ------------------------------------------
Say "==> Поднимаю Docker-стек (Continuwuity, Element, Caddy)..."
Push-Location $dockerDir
try {
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { Die "docker compose up завершился с ошибкой." }
} finally { Pop-Location }

# Брокер ходит на https://agentschat.local - ждём, пока Caddy примет на 443.
Say "==> Жду готовности Matrix-сервера (порт 443)..."
$ready = $false
foreach ($i in 1..30) { if (Test-Port 443) { $ready = $true; break }; Start-Sleep -Seconds 2 }
if (-not $ready) {
    Write-Host "ПРЕДУПРЕЖДЕНИЕ: 443 не отвечает за 60с. Проверьте: docker compose -f docker/docker-compose.yml logs continuwuity" -ForegroundColor Yellow
}

# --- 2. Брокер ---------------------------------------------------------
$running = $false
if (Test-Path $pidFile) {
    $existing = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($existing) { $existing = $existing.Trim() }
    if ($existing -and (Get-Process -Id ([int]$existing) -ErrorAction SilentlyContinue)) {
        $running = $true
        Say "==> Брокер уже работает (PID $existing) - второй не запускаю."
    }
}

if (-not $running) {
    if (Test-Port $brokerPort) {
        Die "порт $brokerPort занят, но pid-файла нет - его держит чужой процесс. Остановите прежний брокер и повторите."
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $pidFile) | Out-Null
    Say "==> Запускаю брокер (лог: bridge/broker.log)..."
    $proc = Start-Process -FilePath $python `
        -ArgumentList '-X','utf8','-m','sessionchat.broker','--config','config.yaml','--verbose' `
        -WorkingDirectory $bridgeDir `
        -RedirectStandardError $logFile `
        -WindowStyle Hidden -PassThru
    $proc.Id | Out-File -FilePath $pidFile -Encoding ascii

    $up = $false
    foreach ($i in 1..10) {
        if ($proc.HasExited) { Die "брокер завершился при старте (код $($proc.ExitCode)). Смотрите bridge/broker.log." }
        if (Test-Port $brokerPort) { $up = $true; break }
        Start-Sleep -Seconds 1
    }
    if ($up) { Say "==> Брокер готов (PID $($proc.Id), порт $brokerPort)." }
    else { Write-Host "ПРЕДУПРЕЖДЕНИЕ: брокер не открыл порт $brokerPort за 10с. Смотрите bridge/broker.log." -ForegroundColor Yellow }
}

Write-Host ""
Write-Host "Готово. Element Web: https://agentschat.local" -ForegroundColor Green
Write-Host "Дальше в каждой сессии CLI вызвать /chatlogin. Остановить всё: .\stop.ps1" -ForegroundColor Green

if ($Logs) {
    Say "==> Лог брокера (Ctrl+C - выйти, стенд останется поднятым):"
    Get-Content $logFile -Wait -Tail 20
}
