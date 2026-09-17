# =====================================================
#  ParkingSystem Auto-Start (idempotent, logged)
#  Runs at Windows logon via Task Scheduler.
# =====================================================
 $ProjectPath = "D:\Projects\ParkingSystem"
 $LogDir      = "$ProjectPath\logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null

function Log($m) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
    $line | Tee-Object -FilePath "$LogDir\autostart.log" -Append
}

function Test-Port([int]$p) {
    [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

Log "===== ParkingSystem auto-start started ====="

# --- 1) wait for Docker engine (max 10 min) ---
Log "waiting for Docker engine..."
 $deadline = (Get-Date).AddMinutes(10)
 $dockerOk = $false
while ((Get-Date) -lt $deadline) {
    docker info 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $dockerOk = $true; break }
    Start-Sleep -Seconds 10
}
if (-not $dockerOk) { Log "ABORT: Docker engine not available after 10 min"; exit 1 }
Log "Docker engine OK"

# --- 2) infra containers ---
docker compose -f "$ProjectPath\docker-compose.yml" up -d 2>&1 | ForEach-Object { Log "compose: $_" }
Log "docker compose up -d done"

# --- 3) backend (idempotent) ---
if (Test-Port 8000) {
    Log "backend already running (port 8000)"
} else {
    Log "starting backend..."
    Start-Process -WindowStyle Hidden powershell -ArgumentList @(
        "-NoProfile","-ExecutionPolicy","Bypass","-Command",
        "Set-Location '$ProjectPath\backend'; " +
        "& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 0.0.0.0 --port 8000 " +
        "*> '$LogDir\backend.log'"
    )
    $up = $false
    for ($i = 1; $i -le 240; $i++) {
        Start-Sleep -Seconds 2
        try { Invoke-RestMethod "http://localhost:8000/health/live" -TimeoutSec 2 | Out-Null; $up = $true; break } catch { }
    }
    if ($up) { Log "backend UP (health/live 200)" }
    else     { Log "backend FAILED - see logs\backend.log" }
}

# --- 4) frontend (idempotent) ---
if (Test-Port 5173) {
    Log "frontend already running (port 5173)"
} else {
    Log "starting frontend..."
    Start-Process -WindowStyle Hidden powershell -ArgumentList @(
        "-NoProfile","-ExecutionPolicy","Bypass","-Command",
        "Set-Location '$ProjectPath\frontend'; npm run dev *> '$LogDir\frontend.log'"
    )
    $up = $false
    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Seconds 2
        try { Invoke-RestMethod "http://localhost:5173" -TimeoutSec 2 | Out-Null; $up = $true; break } catch { }
    }
    if ($up) { Log "frontend UP" }
    else     { Log "frontend FAILED - see logs\frontend.log" }
}

# --- 5) gate-agent (idempotent) ---
if (Test-Port 8091) {
    Log "gate-agent already running (port 8091)"
} else {
    Log "starting gate-agent..."
    Start-Process -WindowStyle Hidden powershell -ArgumentList @(
        "-NoProfile","-ExecutionPolicy","Bypass","-Command",
        "Set-Location '$ProjectPath\gate-agent'; " +
        "& '.\.venv\Scripts\python.exe' -m agent.main *> '$LogDir\agent.log'"
    )
    Start-Sleep -Seconds 5
    if (Test-Port 8091) { Log "gate-agent UP" } else { Log "gate-agent port not up yet (non-fatal)" }
}

# --- 6) final summary ---
 $s = @()
 $s += "backend : " + $(if (Test-Port 8000) { "UP" } else { "DOWN" })
 $s += "frontend: " + $(if (Test-Port 5173) { "UP" } else { "DOWN" })
 $s += "agent   : " + $(if (Test-Port 8091) { "UP" } else { "DOWN" })
 $s | ForEach-Object { Log $_ }
Log "===== auto-start finished ====="