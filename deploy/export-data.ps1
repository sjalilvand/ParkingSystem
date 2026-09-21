# =====================================================
#  ParkingSystem - Export data from DEV machine
#  Run:  powershell -File deploy\export-data.ps1
#  خروجی: پوشه parking-migration کنار پروژه + فایل zip روی دسکتاپ
# =====================================================
 $ErrorActionPreference = "Stop"
 $dest = Join-Path $PSScriptRoot "..\parking-migration"
New-Item -ItemType Directory -Force $dest | Out-Null

Write-Host "=== [1] Dump دیتابیس PostgreSQL ===" -ForegroundColor Cyan
 $pg = docker ps --filter "name=parking-postgres" --format "{{.Names}}"
if (-not $pg) { Write-Host "کانتینر parking-postgres روشن نیست — docker compose up -d بزنید" -ForegroundColor Red; exit 1 }
docker exec $pg pg_dump -U parking parking_db -f /tmp/parking_backup.sql
docker cp "${pg}:/tmp/parking_backup.sql" (Join-Path $dest "parking_backup.sql")
 $size = [math]::Round((Get-Item (Join-Path $dest "parking_backup.sql")).Length/1KB,1)
Write-Host "SQL dump OK ($size KB)" -ForegroundColor Green

Write-Host "=== [2] Mirror فایل‌های MinIO (عکس‌ها) ===" -ForegroundColor Cyan
 $mdest = Join-Path $dest "minio"
New-Item -ItemType Directory -Force $mdest | Out-Null
docker run --rm -v "${mdest}:/backup" --entrypoint /bin/sh minio/mc -c `
  "mc alias set src http://host.docker.internal:9000 minioadmin minioadmin && mc mirror --overwrite src/parking-files /backup"
 $files = (Get-ChildItem $mdest -Recurse -File -ErrorAction SilentlyContinue).Count
Write-Host "MinIO mirror OK ($files file(s))" -ForegroundColor Green

Write-Host "=== [3] ساخت zip ===" -ForegroundColor Cyan
 $zip = "$env:USERPROFILE\Desktop\parking-migration-$(Get-Date -Format yyyyMMdd).zip"
Compress-Archive -Path "$dest\*" -DestinationPath $zip -Force
Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
Write-Host "پوشه مهاجرت : $dest"
Write-Host "فایل zip    : $zip"
Write-Host "این zip را به سرور منتقل کنید (شبکه/فلش) و از حالت فشرده خارج کنید."