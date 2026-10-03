#Requires -Version 5.1
$ErrorActionPreference = 'Stop'

$startScript = (Join-Path $PSScriptRoot 'start.ps1').Replace("'", "''")
$command = "& '$startScript' -Logs"

Start-Process -FilePath 'powershell.exe' `
    -ArgumentList '-NoProfile', '-NoExit', '-Command', "`"$command`"" `
    -WorkingDirectory $PSScriptRoot `
    -WindowStyle Normal
