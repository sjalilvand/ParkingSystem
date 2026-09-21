# =====================================================
#  ParkingSystem - Import data on SERVER
#  اجرا فقط بعد از:  docker compose -f docker-compose.prod.yml --env-file .env.prod up -d postgres
#  Run from project root:  powershell -File deploy\import-data.ps1 -BackupDir "C:\path\parking-migration"
# =====================================================
param([string]$BackupDir = "")
 $ErrorActionPreference = "Stop"
 $root = Split-Path $PSScriptRoot -Parent
Set-Location $root

if (-not $BackupDir) { $BackupDir = Read-Host "مسیر پوشه parking-migration (حاوی parking_backup.sql و minio)" }
 $sql  = Join-Path $BackupDir "parking_backup.sql"
 $mdir = Join-Path $BackupDir "minio"
if (-not (Test-Path $sql))  { Write-Host "پیدا نشد: $sql" -ForegroundColor Red; exit 1 }

# خواندن مقادیر از .env.prod
 $envMap = @{}
Get-Content (Join-Path $root ".env.prod") | ForEach-Object {
    if ($_ -match "^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$") { $envMap[$Matches[1]] = $Matches[2].Trim() }
}
 $pgUser = $envMap["POSTGRES_USER"];  $pgDb = $envMap["POSTGRES_DB"]
 $mUser  = $envMap["MINIO_ACCESS_KEY"]; $mPass = $envMap["MINIO_SECRET_KEY"]
 $cmp = "docker compose -f docker-compose.prod.yml"

Write-Host "=== [1] بالا آوردن postgres ===" -ForegroundColor Cyan
Invoke-Expression "$cmp --env-file .env.prod up -d postgres"
Write-Host "waiting healthy..." -ForegroundColor DarkGray
for ($i=1; $i -le 60; $i++) {
    $h = docker inspect --format "{{.State.Health.Status}}" (docker compose -f docker-compose.prod.yml ps -q postgres) 2>$null
    if ($h -eq "healthy") { break }
    Start-Sleep -Seconds 3
}
Write-Host "postgres: $h" -ForegroundColor Green

Write-Host "=== [2] Restore دیتابیس ===" -ForegroundColor Cyan
 $cid = docker compose -f docker-compose.prod.yml ps -q postgres
docker cp $sql "${cid}:/tmp/parking_backup.sql"
docker compose -f docker-compose.prod.yml exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=0 -f /tmp/parking_backup.sql 2>&1 | Select-Object -Last 5
 $cnt = docker compose -f docker-compose.prod.yml exec -T postgres psql -U $pgUser -d $pgDb -t -c "SELECT count(*) FROM vehicles;"
Write-Host "vehicles rows restored: $($cnt.Trim())" -ForegroundColor Green

Write-Host "=== [3] Restore فایل‌های MinIO ===" -ForegroundColor Cyan
 $net = (docker network ls --format "{{.Name}}" | Select-String "psnet" | Select-Object -First 1).ToString()
docker run --rm --network $net -v "${mdir}:/backup" --entrypoint /bin/sh minio/mc -c `
  "mc alias set dst http://minio:9000 $mUser $mPass && mc mirror --overwrite /backup dst/parking-files"
Write-Host "MinIO restore OK" -ForegroundColor Green

Write-Host ""
Write-Host "=== DONE — مرحله بعد ===" -ForegroundColor Green
Write-Host "docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build"