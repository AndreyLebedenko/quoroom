param(
    [ValidateSet('Start', 'Stop', 'Status')]
    [string]$Action = 'Status'
)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$config = Join-Path $PSScriptRoot 'coordination.yaml'
if ($Action -eq 'Start') {
    $logs = Join-Path $PSScriptRoot 'logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $process = Start-Process -FilePath $python -WindowStyle Hidden -PassThru `
        -WorkingDirectory $PSScriptRoot `
        -ArgumentList @('-X', 'utf8', '-u', '-m', 'coordination.service', '--config', ('"' + $config + '"')) `
        -RedirectStandardOutput (Join-Path $logs 'coordination.stdout.log') `
        -RedirectStandardError (Join-Path $logs 'coordination.log')
    Write-Output "Started PID $($process.Id). Check Status and logs\coordination.log."
} else {
    & $python -X utf8 -m coordination.service --config $config --action $Action.ToLowerInvariant()
    if ($LASTEXITCODE -ne 0) { throw "Coordination command failed: $LASTEXITCODE" }
}
