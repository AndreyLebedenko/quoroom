# Запускает все три моста в отдельных окнах PowerShell.
# Предполагается, что venv уже создан и активирован / доступен по пути ниже.
# Запускать из папки bridge/.

$venvPython = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $venvPython = "python"  # fallback на системный python, если venv не создавали
}

$agents = @("claude-code", "codex", "opencode")

foreach ($agent in $agents) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", `
        "$venvPython matrix_bridge.py --config config.yaml --agent $agent"
}
