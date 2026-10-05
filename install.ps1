#Requires -Version 5.1
<#
  Quoroom - установка и удаление одной машиной одной командой:

    .\install.ps1                                # спросит роль
    .\install.ps1 --role both
    .\install.ps1 --role participant --remove
    .\install.ps1 --role server --remove --purge
#>
$ErrorActionPreference = 'Continue'

$root          = $PSScriptRoot
$bridge        = Join-Path $root 'bridge'
$layer         = Join-Path $bridge 'sessionchat\installer\__main__.py'
$missingPython = 9

$language = 'en'
for ($position = 0; $position -lt $args.Count; $position++) {
    $argument = "$($args[$position])"
    if ($argument -ceq '--lang' -and $position + 1 -lt $args.Count) {
        $language = "$($args[$position + 1])"
    } elseif ($argument.StartsWith('--lang=', [System.StringComparison]::Ordinal)) {
        $language = $argument.Substring('--lang='.Length)
    }
}

if ($language -ceq 'ru') {
    $errorLabel = 'ОШИБКА'
    $texts = @{
        layer  = 'общий слой установщика не найден: {0}. Запускайте скрипт из корня репозитория Quoroom.'
        python = 'подходящий Python не найден: нужен 3.10 или новее (bridge/pyproject.toml, requires-python). Установите его и повторите: winget install Python.Python.3.11'
        start  = 'не удалось запустить {0} : {1}'
    }
} else {
    $errorLabel = 'ERROR'
    $texts = @{
        layer  = 'the shared installer layer was not found: {0}. Run the script from the root of the Quoroom repository.'
        python = 'no suitable Python found: 3.10 or newer is required (bridge/pyproject.toml, requires-python). Install it and run again: winget install Python.Python.3.11'
        start  = 'could not start {0} : {1}'
    }
}

function Die($key, $values) {
    Write-Host "${errorLabel}: $($texts[$key] -f @($values))" -ForegroundColor Red
    exit $missingPython
}

function Quote-Arg([string]$value) {
    if ($value -eq '') { return '""' }
    if ($value -notmatch '[\s"]' -and $value -notmatch '\\$') { return $value }
    $escaped = $value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

if (-not (Test-Path -LiteralPath $layer)) {
    Die 'layer' @($layer)
}

$marker = 'quoroom-python='
$probe = "import base64, sys; print('$marker' + base64.b64encode(sys.executable.encode('utf-8')).decode('ascii')); raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
$candidates = @(
    @{ exe = 'py'; pre = @('-3') },
    @{ exe = 'python'; pre = @() }
)

$interpreter = $null
foreach ($candidate in $candidates) {
    if (-not (Get-Command $candidate.exe -ErrorAction SilentlyContinue)) { continue }
    $check = $candidate.pre + @('-c', $probe)
    $reported = @(& $candidate.exe @check 2>$null)
    if ($LASTEXITCODE -ne 0) { continue }
    $answer = @($reported | Where-Object { "$_".StartsWith($marker) }) | Select-Object -Last 1
    if (-not $answer) { continue }
    try {
        $interpreter = [System.Text.Encoding]::UTF8.GetString(
            [System.Convert]::FromBase64String("$answer".Substring($marker.Length).Trim()))
        break
    } catch {
        $interpreter = $null
    }
}
if (-not $interpreter) {
    Die 'python' @()
}

$run = @('-X', 'utf8', '-m', 'sessionchat.installer') + @($args)
$start = New-Object System.Diagnostics.ProcessStartInfo
$start.FileName = $interpreter
$start.Arguments = (($run | ForEach-Object { Quote-Arg $_ }) -join ' ')
$start.UseShellExecute = $false
$start.EnvironmentVariables['PYTHONPATH'] = $bridge
$start.EnvironmentVariables['PYTHONUTF8'] = '1'
$start.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
try {
    $process = [System.Diagnostics.Process]::Start($start)
} catch {
    Die 'start' @($interpreter, $_.Exception.Message)
}
$process.WaitForExit()
exit $process.ExitCode