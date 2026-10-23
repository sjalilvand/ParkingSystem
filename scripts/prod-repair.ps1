# ============================================================================
#  prod-repair.ps1 — تعمیر استقرار Production پارکینگ‌سیستم (برج‌های ارکیده)
#
#  چه کاری می‌کند؟
#    ۱) رمز کاربر پایگاه‌داده را با POSTGRES_PASSWORD فایل .env.prod همگام
#       می‌کند (ALTER USER) — رفع خطای InvalidPasswordError بدون آسیب به داده‌ها
#    ۲) (اختیاری) با سوییچ -Port پورت انتشار را در .env.prod عوض می‌کند
#    ۳) backend و nginx را همیشه با --env-file .env.prod دوباره بالا می‌آورد
#       (برای بک‌اند build هم می‌زند تا کد جدید داخل ایمیج برود)
#    ۴) سلامت را روی http://127.0.0.1:<APP_PORT>/health/live چک می‌کند
#
#  استفاده:
#     .\scripts\prod-repair.ps1                # فقط رفع خطای رمز دیتابیس
#     .\scripts\prod-repair.ps1 -Port 8085     # رفع رمز + انتقال UI به پورت 8085
#     .\scripts\prod-repair.ps1 -SkipBuild     # بدون build مجدد ایمیج بک‌اند
#
#  قانون طلایی: هر دستور docker compose دستی باید --env-file .env.prod داشته
#  باشد؛ در غیر این صورت ${POSTGRES_PASSWORD} و ${APP_PORT} درست resolve
#  نمی‌شوند و همین باعث InvalidPasswordError می‌شود.
# ============================================================================

param(
    [int]$Port = 0,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)   # پایپ UTF-8 به دستورهای native

# ---------- مسیرها ----------
$root    = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$yml     = Join-Path $root "docker-compose.prod.yml"
$envFile = Join-Path $root ".env.prod"

Write-Host ""
Write-Host "=== ParkingSystem — prod-repair ===" -ForegroundColor Cyan
Write-Host "پروژه: $root" -ForegroundColor Gray

if (-not (Test-Path $yml)) { Write-Host "✗ docker-compose.prod.yml پیدا نشد" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $envFile)) {
    Write-Host "✗ .env.prod نیست — از .env.prod.example بسازید (راهنما: docs/guides/server-deployment-guide.html)" -ForegroundColor Red
    exit 1
}

# موتور داکر در دسترس است؟
& docker info --format "{{.ServerVersion}}" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ موتور Docker در دسترس نیست — Docker Desktop را باز کنید تا Engine سبز شود، بعد دوباره تلاش کنید." -ForegroundColor Red
    exit 1
}

# ---------- خواندن .env.prod (خودکار تشخیص BOM/UTF-16) ----------
$lines = [System.IO.File]::ReadAllLines($envFile)
$vals = @{}
foreach ($ln in $lines) {
    if ($ln -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $vals[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'")
    }
}
$pgUser = $vals['POSTGRES_USER']; if (-not $pgUser) { $pgUser = "parking" }
$pgDb   = $vals['POSTGRES_DB'];   if (-not $pgDb)   { $pgDb   = "parking_db" }
$pgPass = $vals['POSTGRES_PASSWORD']
if (-not $pgPass) {
    Write-Host "✗ POSTGRES_PASSWORD در .env.prod خالی/ناموجود است — اول آن را تنظیم کنید." -ForegroundColor Red
    exit 1
}
if ($pgPass -match '[:/@?#\s]') {
    Write-Host "⚠ POSTGRES_PASSWORD نویسه‌های ناامن برای URL دارد ( : / @ ? # فاصله ) — این رمز داخل DATABASE_URL هم می‌رود و ممکن است اتصال را خراب کند." -ForegroundColor Yellow
    Write-Host "  پیشنهاد: رمز فقط حروف و عدد باشد؛ در .env.prod اصلاح و این اسکریپت را دوباره اجرا کنید." -ForegroundColor Yellow
}

# ---------- تغییر پورت (اختیاری) ----------
if ($Port -gt 0) {
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^\s*APP_PORT\s*=') { $lines[$i] = "APP_PORT=$Port"; $found = $true }
    }
    if (-not $found) { $lines += "APP_PORT=$Port" }
    [System.IO.File]::WriteAllLines($envFile, $lines, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "✔ APP_PORT در .env.prod روی $Port تنظیم شد." -ForegroundColor Green
}

$appPort = 8880
if ($vals['APP_PORT'] -match '^\d+$') { $appPort = [int]$vals['APP_PORT'] }
if ($Port -gt 0) { $appPort = $Port }

# ---------- هشدار فایل .env مزاحم در ریشه (تداخل interpolation) ----------
$rootEnv = Join-Path $root ".env"
if (Test-Path $rootEnv) {
    $rv = @{}
    foreach ($ln in [System.IO.File]::ReadAllLines($rootEnv)) {
        if ($ln -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { $rv[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'") }
    }
    if ($rv['POSTGRES_PASSWORD'] -and $rv['POSTGRES_PASSWORD'] -ne $pgPass) {
        Write-Host "⚠ فایل .env ریشهٔ پروژه POSTGRES_PASSWORD متفاوتی دارد؛ دستورهای دستی docker compose بدون --env-file همان را می‌خوانند و خطای رمز برمی‌گردد." -ForegroundColor Yellow
        Write-Host "  پیشنهاد:  Rename-Item .env .env.bak   (تا تداخل پیش نیاید)" -ForegroundColor Yellow
    }
}

$compose = @("compose", "-f", $yml, "--env-file", $envFile)

Write-Host ""
Write-Host "=== [۱/۴] بالا آوردن postgres و منتظر healthy شدن ===" -ForegroundColor Yellow
& docker @compose up -d postgres
if ($LASTEXITCODE -ne 0) { Write-Host "✗ docker compose ناموفق — لاگ بالا را بفرستید." -ForegroundColor Red; exit 1 }
$cid = $null
$healthy = $false
for ($i = 0; $i -lt 30; $i++) {
    if (-not $cid) { $cid = (& docker @compose ps -q postgres) | Select-Object -First 1 }
    if ($cid) {
        $st = (& docker inspect --format "{{.State.Health.Status}}" $cid 2>$null)
        if ($st -eq "healthy") { $healthy = $true; break }
    }
    Start-Sleep -Seconds 2
}
if ($healthy) { Write-Host "✔ postgres سالم است." -ForegroundColor Green }
else { Write-Host "⚠ postgres بعد از ۶۰ ثانیه healthy نشد — ادامه می‌دهیم…" -ForegroundColor Yellow }

Write-Host ""
Write-Host "=== [۲/۴] همگام‌سازی رمز دیتابیس با .env.prod (ALTER USER) ===" -ForegroundColor Yellow
$escaped = $pgPass -replace "'", "''"
$sql = "ALTER USER $pgUser WITH PASSWORD '$escaped';"
$sql | & docker @compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  تلاش دوم با دیتابیس postgres (اگر POSTGRES_DB ساخته نشده) …" -ForegroundColor Gray
    $sql | & docker @compose exec -T postgres psql -U $pgUser -d postgres -v ON_ERROR_STOP=1
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ ALTER USER ناموفق — خروجی بالا را برای پشتیبانی بفرستید." -ForegroundColor Red
    exit 1
}
Write-Host "✔ رمز کاربر «$pgUser» با .env.prod همگام شد (داده‌ها دست‌نخورده)." -ForegroundColor Green

Write-Host ""
Write-Host "=== [۳/۴] build بک‌اند + اجرای مجدد backend و nginx (با --env-file) ===" -ForegroundColor Yellow
if (-not $SkipBuild) {
    & docker @compose build backend
    if ($LASTEXITCODE -ne 0) { Write-Host "⚠ build بک‌اند ناموفق — با ایمیج قبلی ادامه می‌دهیم…" -ForegroundColor Yellow }
}
& docker @compose up -d backend nginx
if ($LASTEXITCODE -ne 0) { Write-Host "✗ اجرای سرویس‌ها ناموفق — لاگ بالا را بفرستید." -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "=== [۴/۴] بررسی سلامت روی پورت $appPort ===" -ForegroundColor Yellow
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$appPort/health/live" -TimeoutSec 3
        if ($r.status -eq "ok") { $ok = $true; break }
    } catch {}
}

# تشخیص IP شبکهٔ داخلی برای نمایش آدرس
$lanIp = "192.168.100.2"
try {
    $ipObj = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.InterfaceAlias -notlike "*Loopback*" -and $_.InterfaceAlias -notlike "vEthernet*" } |
        Select-Object -First 1
    if ($ipObj) { $lanIp = $ipObj.IPAddress }
} catch {}
$portPart = ""
if ($appPort -ne 80) { $portPart = ":$appPort" }

Write-Host ""
if ($ok) {
    Write-Host "✔ سامانه در حالت production سالم است." -ForegroundColor Green
    & docker @compose ps
    Write-Host ""
    Write-Host "  آدرس روی همین سیستم:    http://localhost$portPart" -ForegroundColor Green
    Write-Host "  آدرس در شبکهٔ داخلی:     http://$lanIp$portPart" -ForegroundColor Green
    Write-Host ""
    Write-Host "  یادآوری: هر دستور docker compose دستی باید --env-file .env.prod داشته باشد." -ForegroundColor Gray
    exit 0
} else {
    Write-Host "✗ سامانه هنوز سالم نیست — ۲۵ خط آخر لاگ بک‌اند:" -ForegroundColor Red
    & docker @compose logs backend --tail 25
    Write-Host ""
    Write-Host "  قانون طلایی: دستورهای دستی compose باید این‌شکلی باشند:" -ForegroundColor Yellow
    Write-Host "    docker compose -f docker-compose.prod.yml --env-file .env.prod up -d" -ForegroundColor Gray
    exit 2
}
