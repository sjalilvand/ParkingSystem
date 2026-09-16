 $ProjectRoot = $PSScriptRoot
Push-Location $ProjectRoot
docker compose up -d
Pop-Location
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location (Join-Path '$ProjectRoot' 'backend'); .\.venv\Scripts\Activate.ps1; python -m uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location (Join-Path '$ProjectRoot' 'gate-agent'); .\.venv\Scripts\Activate.ps1; `$env:PYTHONIOENCODING='utf-8'; python -m agent.main"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location (Join-Path '$ProjectRoot' 'frontend'); npm run dev"
Write-Host "Backend: http://localhost:8000/api/docs | Frontend: http://localhost:5173 | Agent: 8091"