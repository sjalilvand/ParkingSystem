Set-Location (Join-Path $PSScriptRoot "backend")
.\.venv\Scripts\Activate.ps1
Write-Host "Swagger: http://localhost:8000/api/docs"
python -m uvicorn app.main:app --reload --port 8000