# ============================================================================
#  setup-google-sync.ps1 — نصب یک‌مرحله‌ای همگام‌سازی Google Sheets
#  (الحاقیه §۴ — راهنمای کامل: docs/google-sheets-setup.md)
#
#  استفاده:
#    .\scripts\setup-google-sync.ps1 -KeyPath .\secrets\service-account.json
#    .\scripts\setup-google-sync.ps1 -KeyPath C:\keys\sa.json -Worksheet "خودروها" -SpreadsheetId 1Zbi...
#
#  کارهایی که می‌کند:
#    [۱] اعتبارسنجی فایل JSON حساب سرویس (client_email/private_key)
#    [۲] ساخت پوشهٔ secrets و کپی امن فایل (افزودن به .gitignore)
#    [۳] نوشتن تنظیمات در backend\.env (بدون بازنویسی بقیه)
#    [۴] تست اتصال واقعی به شیت از طریق API بک‌اند (در صورت بالابودن)
# ============================================================================
param(
    [Parameter(Mandatory = $true)]
    [string]$KeyPath,
    [string]$Worksheet = "خودروها",
    [string]$SpreadsheetId = "1ZbiQl_9nab-CH0uR1i9dq6pevcCvY0SfyUuxpIyEjQQ",
    [int]$SyncHour = 3
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$backend = Join-Path $root "backend"
$secretsDir = Join-Path $root "secrets"

Write-Host ""
Write-Host "=== نصب همگام‌سازی Google Sheets ===" -ForegroundColor Cyan

# ---------- [۱] اعتبارسنجی فایل کلید ----------
if (-not (Test-Path $KeyPath)) {
    Write-Host "  ✗ فایل کلید یافت نشد: $KeyPath" -ForegroundColor Red
    Write-Host "    راهنما: docs\google-sheets-setup.md گام ۱" -ForegroundColor Yellow
    exit 1
}
$keyJson = Get-Content -Raw -Encoding UTF8 $KeyPath
try {
    $sa = $keyJson | ConvertFrom-Json
} catch {
    Write-Host "  ✗ فایل JSON نامعتبر است: $_" -ForegroundColor Red
    exit 1
}
if (-not $sa.client_email -or -not $sa.private_key) {
    Write-Host "  ✗ فایل، حساب سرویس نیست (client_email/private_key ندارد)" -ForegroundColor Red
    exit 1
}
Write-Host "  [۱] کلید معتبر است — حساب سرویس: $($sa.client_email)" -ForegroundColor Green

# ---------- [۲] کپی امن به secrets/ ----------
if (-not (Test-Path $secretsDir)) { New-Item -ItemType Directory -Path $secretsDir | Out-Null }
$destKey = Join-Path $secretsDir "service-account-readonly.json"
if ((Resolve-Path $KeyPath).Path -ne (Resolve-Path -LiteralPath $destKey -ErrorAction SilentlyContinue)) {
    Copy-Item $KeyPath $destKey -Force
}
$gitignore = Join-Path $root ".gitignore"
if (Test-Path $gitignore) {
    $gi = Get-Content -Raw $gitignore
    if ($gi -notmatch "secrets/") { Add-Content $gitignore "`nsecrets/" }
} else {
    Set-Content $gitignore "secrets/"
}
Write-Host "  [۲] کلید در secrets\service-account-readonly.json کپی شد (خارج از git)" -ForegroundColor Green

# ---------- [۳] نوشتن .env بک‌اند ----------
$envFile = Join-Path $backend ".env"
$settings = [ordered]@{
    "GOOGLE_SERVICE_ACCOUNT_FILE" = "secrets/service-account-readonly.json"
    "GOOGLE_SHEETS_SPREADSHEET_ID" = $SpreadsheetId
    "GOOGLE_SHEETS_WORKSHEET"      = $Worksheet
    "VEHICLE_SYNC_HOUR"            = $SyncHour
    "GOOGLE_SHEETS_ENABLED"        = "true"
    "VEHICLE_SYNC_SCHEDULER"       = "true"
}
$envLines = @()
if (Test-Path $envFile) { $envLines = Get-Content $envFile }
foreach ($k in $settings.Keys) {
    $envLines = @($envLines | Where-Object { $_ -notmatch "^\s*$([regex]::Escape($k))\s*=" })
    $envLines += "$k=$($settings[$k])"
}
Set-Content -Path $envFile -Value $envLines -Encoding UTF8
Write-Host "  [۳] backend\.env به‌روزرسانی شد (worksheet=«$Worksheet»، ساعت اجرا=$SyncHour:۰۰ تهران)" -ForegroundColor Green

# ---------- [۴] تست اتصال ----------
Write-Host "  [۴] تست اتصال به شیت…" -ForegroundColor Yellow
$healthOk = $false
try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/live" -TimeoutSec 3
    $healthOk = ($h.status -eq "ok")
} catch {}
if ($healthOk) {
    try {
        # توکن ادمین — اگر رمز admin را عوض کرده‌اید، دو خط زیر را ویرایش کنید
        $login = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/auth/login" -Method Post `
            -ContentType "application/json" -Body '{"username":"admin","password":"Admin@1234"}' -TimeoutSec 10
        $token = $login.access_token
        if (-not $token -and $login.data) { $token = $login.data.access_token }
        $res = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/integrations/google-sheets/test" `
            -Method Post -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 40
        if ($res.ok) {
            Write-Host "  ✔ اتصال موفق! شیت: «$($res.title)» | تب‌ها: $($res.tabs -join '، ')" -ForegroundColor Green
            Write-Host "    گام بعدی: پنل → همگام‌سازی خودروها → «اجرای آزمایشی (Dry-run)»" -ForegroundColor Cyan
        } else {
            Write-Host "  ⚠ اتصال ناموفق: $($res.error)" -ForegroundColor Yellow
            Write-Host "    شیت را با $($sa.client_email) به‌صورت Viewer به‌اشتراک گذاشته‌اید؟ (گام ۲ راهنما)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  ⚠ تست از طریق API ناموفق: $_" -ForegroundColor Yellow
        Write-Host "    بک‌اند را با UPDATE-AND-RUN.ps1 بالا بیاورید و از پنل «تست اتصال» بزنید." -ForegroundColor Gray
    }
} else {
    Write-Host "  ⚠ بک‌اند بالا نیست — تنظیمات ذخیره شد؛ پس از اجرای UPDATE-AND-RUN.ps1 از پنل «تست اتصال» بزنید." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "=== پایان نصب ===" -ForegroundColor Cyan
