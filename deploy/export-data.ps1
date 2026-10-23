# =====================================================
#  ParkingSystem - Export data from LAPTOP (prod or dev stack)
#  Run:  powershell -File deploy\export-data.ps1
#  خروجی: پوشه parking-migration کنار پروژه + فایل zip روی دسکتاپ
#  تشخیص خودکار استک: اول prod (parkingsystem-prod-postgres-1) بعد dev (parking-postgres)
# =====================================================
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$root = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $root "parking-migration"
New-Item -ItemType Directory -Force $dest | Out-Null

# ---------- [۰] تشخیص استک فعال ----------
$pg = (docker ps --filter "name=parkingsystem-prod-postgres" --format "{{.Names}}" | Select-Object -First 1)
$stack = "prod"
if (-not $pg) {
    $pg = (docker ps --filter "name=parking-postgres" --format "{{.Names}}" | Select-Object -First 1)
    $stack = "dev"
}
if (-not $pg) {
    Write-Host "هیچ کانتینر postgres روشن نیست — اول docker compose up -d بزنید" -ForegroundColor Red
    exit 1
}
Write-Host "استک: $stack | کانتینر: $pg" -ForegroundColor Cyan

# ---------- خواندن .env.prod (برای استک prod) ----------
$envMap = @{}
if ($stack -eq "prod") {
    $envFile = Join-Path $root ".env.prod"
    if (-not (Test-Path $envFile)) { Write-Host ".env.prod پیدا نشد" -ForegroundColor Red; exit 1 }
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$") { $envMap[$Matches[1]] = $Matches[2].Trim() }
    }
}
$pgUser = if ($envMap["POSTGRES_USER"]) { $envMap["POSTGRES_USER"] } else { "parking" }
$pgDb   = if ($envMap["POSTGRES_DB"])   { $envMap["POSTGRES_DB"] }   else { "parking_db" }

Write-Host "=== [1] Dump دیتابیس PostgreSQL ===" -ForegroundColor Cyan
docker exec $pg pg_dump -U $pgUser $pgDb -f /tmp/parking_backup.sql
if ($LASTEXITCODE -ne 0) { Write-Host "pg_dump ناموفق بود" -ForegroundColor Red; exit 1 }
docker cp "${pg}:/tmp/parking_backup.sql" (Join-Path $dest "parking_backup.sql")
$size = [math]::Round((Get-Item (Join-Path $dest "parking_backup.sql")).Length/1KB,1)
Write-Host "SQL dump OK ($size KB)" -ForegroundColor Green

Write-Host "=== [2] Mirror فایل‌های MinIO (عکس‌ها) ===" -ForegroundColor Cyan
$mdest = Join-Path $dest "minio"
New-Item -ItemType Directory -Force $mdest | Out-Null
$mcOk = $false
if ($stack -eq "prod") {
    # در استک prod مینيو فقط داخل شبکهٔ psnet در دسترس است (پورت میزبان ندارد)
    $mUser = if ($envMap["MINIO_ACCESS_KEY"]) { $envMap["MINIO_ACCESS_KEY"] } else { "parkingminio" }
    $mPass = $envMap["MINIO_SECRET_KEY"]
    if (-not $mPass) { Write-Host "MINIO_SECRET_KEY در .env.prod نیست — رد شد" -ForegroundColor Yellow }
    else {
        $net = (docker network ls --format "{{.Name}}" | Where-Object { $_ -like "*psnet*" } | Select-Object -First 1)
        if (-not $net) { Write-Host "شبکهٔ psnet پیدا نشد" -ForegroundColor Yellow }
        else {
            docker run --rm --network $net -v "${mdest}:/backup" --entrypoint /bin/sh minio/mc -c `
              "mc alias set src http://minio:9000 $mUser $mPass && mc mirror --overwrite src/parking-files /backup"
            $mcOk = ($LASTEXITCODE -eq 0)
        }
    }
} else {
    docker run --rm -v "${mdest}:/backup" --entrypoint /bin/sh minio/mc -c `
      "mc alias set src http://host.docker.internal:9000 minioadmin minioadmin && mc mirror --overwrite src/parking-files /backup"
    $mcOk = ($LASTEXITCODE -eq 0)
}
if ($mcOk) {
    $files = (Get-ChildItem $mdest -Recurse -File -ErrorAction SilentlyContinue).Count
    Write-Host "MinIO mirror OK ($files file(s))" -ForegroundColor Green
} else {
    Write-Host "⚠ MinIO mirror ناموفق — دیتابیس سالم است؛ فایل‌ها را می‌توانید بعداً منتقل کنید" -ForegroundColor Yellow
}

Write-Host "=== [3] ساخت zip ===" -ForegroundColor Cyan
$zip = "$env:USERPROFILE\Desktop\parking-migration-$(Get-Date -Format yyyyMMdd).zip"
Compress-Archive -Path "$dest\*" -DestinationPath $zip -Force
Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
Write-Host "پوشه مهاجرت : $dest"
Write-Host "فایل zip    : $zip"
Write-Host "این zip را به سرور منتقل کنید (شبکه/فلش) و از حالت فشرده خارج کنید."
Write-Host "مرحله بعد روی سرور: powershell -File deploy\import-data.ps1 -BackupDir <مسیر پوشه>"
