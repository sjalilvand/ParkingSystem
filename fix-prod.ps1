# ============ fix-prod.ps1 (hardcoded root) ============
 $ErrorActionPreference = "Continue"
 $root = "D:\Projects\ParkingSystem"

 $alpha = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
 $newPass = "Orkid-" + (-join (1..24 | ForEach-Object { $alpha[(Get-Random -Maximum $alpha.Length)] })) + "-V1"

 $envPath = Join-Path $root ".env.prod"
 $lines = @(Get-Content -LiteralPath $envPath)
Write-Host ("env lines read: " + $lines.Count)
 $out = foreach ($l in $lines) {
    if ($l -match "^DEFAULT_ADMIN_PASSWORD\s*=") { "DEFAULT_ADMIN_PASSWORD=$newPass" }
    elseif ($l -match "^APP_PORT\s*=") { "APP_PORT=8880" }
    else { $l }
}
 $foundPass = @($out | Where-Object { $_ -match "^DEFAULT_ADMIN_PASSWORD=" }).Count
 $foundPort = @($out | Where-Object { $_ -match "^APP_PORT=8880" }).Count
if (-not $foundPass) { $out = @($out) + "DEFAULT_ADMIN_PASSWORD=$newPass" }
if (-not $foundPort) { $out = @($out) + "APP_PORT=8880" }
Set-Content -LiteralPath $envPath -Value @($out) -Encoding UTF8
Write-Host "env updated: pass=$foundPass port8880=$foundPort"

 $suspect = @($out | Where-Object { $_ -match "=\S*\$" })
if ($suspect.Count -eq 0) { Write-Host "hygiene scan: none - clean" }
else { $suspect | ForEach-Object { $_ -replace "=(.{4})\S*", "=`$1***" } }

 $credFile = Join-Path $root "logs\prod-admin-credentials.txt"
@"
PROD ADMIN (تغییر دهید پس از اولین ورود!)
URL:  http://localhost:8880
User: admin
Pass: $newPass
Date: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@ | Set-Content -LiteralPath $credFile -Encoding UTF8
Write-Host "creds written"

 $compose = Join-Path $root "docker-compose.prod.yml"
docker compose -f $compose --env-file $envPath up -d --force-recreate backend nginx 2>&1 | Out-Host

 $ok = $false
for ($i = 1; $i -le 60; $i++) {
    Start-Sleep -Seconds 5
    $h = (curl.exe -s --max-time 4 "http://localhost:8880/health/live" 2>$null) -join ""
    if ($h -match '"ok"') { $ok = $true; break }
    Write-Host "waiting prod backend... ($i)"
}
if (-not $ok) {
    Write-Host "STILL DOWN - logs:" -ForegroundColor Red
    docker compose -f $compose --env-file $envPath logs --tail 40 backend 2>&1 | Out-Host
    exit 1
}
Write-Host "prod backend: LIVE on 8880" -ForegroundColor Green

 $dbh = (curl.exe -s --max-time 5 "http://localhost:8880/health/database" 2>$null) -join ""
Write-Host "database health : $dbh"
 $loginBody = '{"username":"admin","password":"' + $newPass + '"}'
 $loginJson = (curl.exe -s -X POST "http://localhost:8880/api/v1/auth/login" -H "Content-Type: application/json" -d $loginBody 2>$null) -join ""
 $atok = ($loginJson | ConvertFrom-Json).access_token
if ($atok) { Write-Host "login with NEW password : OK" -ForegroundColor Green }
else {
    $snippet = if ($loginJson.Length -gt 150) { $loginJson.Substring(0, 150) } else { $loginJson }
    Write-Host "login FAILED: $snippet" -ForegroundColor Red; exit 1
}
foreach ($ep in "vehicle-groups", "rules", "parking/capacity-status") {
    $c = curl.exe -s -o NUL -w "%{http_code}" "http://localhost:8880/api/v1/$ep" -H "Authorization: Bearer $atok"
    Write-Host "prod GET /$ep -> HTTP $c (expect 200)"
}
 $ui = curl.exe -s -o NUL -w "%{http_code}" "http://localhost:8880/"
Write-Host "prod frontend (nginx) -> HTTP $ui (expect 200)"

docker compose -f $compose --env-file $envPath ps 2>&1 | Out-Host
Write-Host "`n=== PROD IS UP ON http://localhost:8880 ===" -ForegroundColor Green
