# ================= ParkingSystem Server Setup =================
 $root = "E:\ParkingSystem"
Set-Location $root
 $ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== [0] Preflight ===" -ForegroundColor Cyan

try { docker info 2>$null | Out-Null; if ($LASTEXITCODE -ne 0) { throw } }
catch { Write-Host "[X] Docker not available - start Docker Desktop (whale icon green) and retry" -ForegroundColor Red; exit 1 }
Write-Host "[OK] Docker engine" -ForegroundColor Green

foreach ($f in @("docker-compose.prod.yml", ".env.prod.example",
                 "backend\Dockerfile", "frontend\Dockerfile", "frontend\nginx.conf")) {
    if (-not (Test-Path (Join-Path $root $f))) {
        Write-Host "[X] Missing file: $f  (project copy incomplete)" -ForegroundColor Red; exit 1
    }
}
Write-Host "[OK] Deployment files" -ForegroundColor Green

 $p80 = Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue
if ($p80) {
    $proc = (Get-Process -Id $p80[0].OwningProcess -ErrorAction SilentlyContinue).ProcessName
    Write-Host "[!] Port 80 in use by: $proc  -> later set APP_PORT=8080 in .env.prod" -ForegroundColor Yellow
}

# ---------- .env.prod ----------
Write-Host ""
Write-Host "=== [1] .env.prod ===" -ForegroundColor Cyan
 $envPath = Join-Path $root ".env.prod"
if (Test-Path $envPath) {
    Write-Host "[OK] .env.prod already exists - keeping it" -ForegroundColor Green
} else {
    $gen = { -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_}) }
    $content = Get-Content (Join-Path $root ".env.prod.example") -Raw
    $content = $content.Replace("<GENERATE-STRONG>", (& $gen))
    $content = [regex]::Replace($content, "<GENERATE>", { param($m) & $gen })
    [System.IO.File]::WriteAllText($envPath, $content, [System.Text.UTF8Encoding]::new($false))
    Write-Host "[OK] .env.prod created (random secrets generated)" -ForegroundColor Green
    Write-Host ""
    Write-Host ">>> IMPORTANT - WRITE THESE DOWN:" -ForegroundColor Yellow
    Get-Content $envPath | ForEach-Object {
        if ($_ -match "^(DEFAULT_ADMIN_PASSWORD|GATE_API_KEY)=") { Write-Host "    $_" }
    }
    $ip = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notmatch "^127\.|^169\.254" } |
        Select-Object -First 1).IPAddress
    if ($ip) {
        $c = Get-Content $envPath -Raw
        $c = $c -replace "CORS_ALLOWED_ORIGINS=.*", "CORS_ALLOWED_ORIGINS=http://$ip"
        [System.IO.File]::WriteAllText($envPath, $c, [System.Text.UTF8Encoding]::new($false))
        Write-Host "[OK] CORS set to http://$ip   (SERVER IP: $ip - note it down)" -ForegroundColor Green
    }
}

# read APP_PORT for base url
 $envMap = @{}
Get-Content $envPath | ForEach-Object {
    if ($_ -match "^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$") { $envMap[$Matches[1]] = $Matches[2].Trim() }
}
 $appPort = if ($envMap["APP_PORT"] -and $envMap["APP_PORT"] -ne "80") { $envMap["APP_PORT"] } else { "80" }
 $base = if ($appPort -eq "80") { "http://localhost" } else { "http://localhost:$appPort" }

 $cmp = "docker compose -f docker-compose.prod.yml --env-file .env.prod"

# ---------- migration? ----------
Write-Host ""
Write-Host "=== [2] Data migration from old machine ===" -ForegroundColor Cyan
Write-Host "Do you have parking_backup.sql (from export-data.ps1 on the old machine)?"
 $ans = Read-Host "y = yes, I have it  |  n = no, start empty (y/n)"
 $hasData = ($ans -eq "y")

if ($hasData) {
    $bd = Read-Host "Path to migration folder (contains parking_backup.sql and minio), e.g. C:\parking-migration"
    $sql = Join-Path $bd "parking_backup.sql"
    if (-not (Test-Path $sql)) { Write-Host "[X] Not found: $sql" -ForegroundColor Red; exit 1 }

    Write-Host "--- starting only postgres ---" -ForegroundColor DarkGray
    Invoke-Expression "$cmp up -d postgres" | Out-Null
    Write-Host "waiting healthy..." -ForegroundColor DarkGray
    $cid = ""
    for ($i = 1; $i -le 60; $i++) {
        Start-Sleep -Seconds 3
        $cid = (Invoke-Expression "$cmp ps -q postgres") 2>$null
        if ($cid) {
            $h = docker inspect --format "{{.State.Health.Status}}" $cid 2>$null
            if ($h -eq "healthy") { break }
        }
    }
    Write-Host "[OK] postgres healthy" -ForegroundColor Green

    Write-Host "--- restoring database ---" -ForegroundColor DarkGray
    docker cp $sql "${cid}:/tmp/parking_backup.sql"
    Invoke-Expression "$cmp exec -T postgres psql -U parking -d parking_db -f /tmp/parking_backup.sql" 2>&1 |
        Select-Object -Last 3
    $cnt = (Invoke-Expression "$cmp exec -T postgres psql -U parking -d parking_db -t -c `"SELECT count(*) FROM vehicles;`"") 2>$null
    Write-Host "[OK] vehicles rows restored: $($cnt.Trim())" -ForegroundColor Green

    $mdir = Join-Path $bd "minio"
    if (Test-Path $mdir) {
        Write-Host "--- restoring MinIO files ---" -ForegroundColor DarkGray
        docker run --rm --network parkingsystem_psnet -v "${mdir}:/backup" --entrypoint /bin/sh minio/mc -c `
            "mc alias set dst http://minio:9000 $($envMap['MINIO_ACCESS_KEY']) $($envMap['MINIO_SECRET_KEY']) && mc mirror --overwrite /backup dst/parking-files"
        Write-Host "[OK] MinIO restore" -ForegroundColor Green
    }
    Write-Host ""
    Write-Host "[!] REMINDER: admin password is the OLD one (Admin@1234) - change it right after login!" -ForegroundColor Yellow
} else {
    Write-Host "-> Empty bootstrap (admin + 463 plate codes + gates auto-created)" -ForegroundColor DarkGray
}

# ---------- full stack ----------
Write-Host ""
Write-Host "=== [3] Full stack up -d --build (first build takes minutes) ===" -ForegroundColor Cyan
Invoke-Expression "$cmp up -d --build"
if ($LASTEXITCODE -ne 0) { Write-Host "[X] build/up failed - see output above" -ForegroundColor Red; exit 1 }

Write-Host "waiting backend health (up to 8 min)..." -ForegroundColor DarkGray
 $ok = $false
for ($i = 1; $i -le 160; $i++) {
    Start-Sleep -Seconds 3
    try { Invoke-RestMethod "$base/health/live" -TimeoutSec 2 | Out-Null; $ok = $true; break } catch { }
    if ($i % 10 -eq 0) { Write-Host "  ...waiting" -ForegroundColor DarkGray }
}
if (-not $ok) {
    Write-Host "[X] backend not UP - logs:" -ForegroundColor Red
    Invoke-Expression "$cmp logs --tail 30 backend"
    exit 1
}
Write-Host "[OK] backend: UP" -ForegroundColor Green

# ---------- summary ----------
 $ip = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notmatch "^127\.|^169\.254" } |
    Select-Object -First 1).IPAddress

Write-Host ""
Write-Host "=================== DEPLOY COMPLETE ===================" -ForegroundColor Green
Invoke-Expression "$cmp ps"
Write-Host ""
Write-Host "Web app : http://$ip$(if($appPort -ne '80'){":$appPort"})" -ForegroundColor White
Write-Host "Health  : $base/health/live" -ForegroundColor White
Write-Host "Swagger : $base/api/docs" -ForegroundColor White
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host " 1) Browser: http://$ip$(if($appPort -ne '80'){":$appPort"})  -> login admin"
Write-Host " 2) Change password (lock icon)"
Write-Host " 3) Firewall (Admin PowerShell):"
Write-Host "    netsh advfirewall firewall add rule name=`"ParkingHTTP`" dir=in action=allow protocol=tcp localport=$appPort"
Write-Host " 4) Gate machine: gate-agent\.env -> CENTRAL_API_URL=http://$ip/api/v1"
Write-Host "=======================================================" -ForegroundColor Green