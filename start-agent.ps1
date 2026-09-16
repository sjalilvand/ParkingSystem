Set-Location (Join-Path $PSScriptRoot "gate-agent")
 $env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\Activate.ps1
python -m agent.main