# ============================================================================
#  UPDATE-AND-RUN.ps1 — ParkingSystem (برج‌های ارکیده)
#  یک‌دستور: دریافت آخرین نسخه + اجرای کامل سامانه (بک‌اند + فرانت + گیت‌ایجنت)
#
#  استفاده:
#     PowerShell:  .\UPDATE-AND-RUN.ps1
#     گزینه‌ها:
#       -SkipPull     فقط اجرا (بدون git pull)
#       -SkipAgent    گیت‌ایجنت را اجرا نکن
#       -Prod         حالت production با docker-compose.prod.yml (.env.prod)
#       -Ocr          فعال‌سازی پلاک‌خوان: INSTALL_OCR=true در .env.prod + build مجدد backend
#                     تست از منوی «آزمایش پلاک‌خوان ← پلاک‌خوان OCR» یا مسیر /plate-test/
#
#  نکتهٔ سرور E:
#     • prod:  .\UPDATE-AND-RUN.ps1 -Prod   → پورت از APP_PORT در .env.prod (E: = 80)
#     • dev:   .\UPDATE-AND-RUN.ps1         → uvicorn:8000 + vite:5173
#     • اگر requirements.txt تغییر کرده باشد، وابستگی‌ها خودکار دوباره نصب می‌شوند
#       (مارکر بر اساس هش فایل است — .deps_ok قدیمی منسوخ)
#
#  پیش‌نیازها (فقط بار اول):
#     backend\.venv  (محیط مجازی پایتون) — خودکار ساخته می‌شود اگر نباشد
#     Node.js پرتابل در tools\node (برای frontend) یا Node نصب‌شدهٔ سیستم
# ============================================================================

param(
    [switch]$SkipPull,
    [switch]$SkipAgent,
    [switch]$Prod,
    [switch]$Ocr
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ---------- تشخیص ریشهٔ پروژه (این فایل در ریشهٔ مخزن است) ----------
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
Write-Host ""
Write-Host "=== ParkingSystem — UPDATE-AND-RUN ===" -ForegroundColor Cyan
Write-Host "پروژه: $root" -ForegroundColor Gray

$backend  = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

# ---------- [۱] دریافت آخرین نسخه ----------
if (-not $SkipPull) {
    Write-Host ""
    Write-Host "=== [۱] git pull (آخرین نسخه از GitHub) ===" -ForegroundColor Yellow
    git fetch origin 2>$null
    $local  = git rev-parse HEAD
    $remote = git rev-parse origin/main 2>$null
    if ($local -ne $remote) {
        # تغییرات محلی موقتاً کنار می‌روند (بازیابی خودکار پس از pull)
        $dirty = (git status --porcelain) -ne $null
        if ($dirty) { git stash push -u -m "auto-stash before update" | Out-Null }
        git pull --ff-only origin main
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  pull --ff-only ناموفق؛ تلاش با rebase…" -ForegroundColor Yellow
            git pull --rebase origin main
        }
        if ($dirty) { git stash pop 2>$null | Out-Null }
    } else {
        Write-Host "  از قبل به‌روز است ($($local.Substring(0,7)))" -ForegroundColor Green
    }
}

# ---------- [۲] محیط مجازی پایتون ----------
Write-Host ""
Write-Host "=== [۲] آماده‌سازی محیط بک‌اند ===" -ForegroundColor Yellow
$pyExe = $null
$cands = @(
    (Join-Path $backend ".venv\Scripts\python.exe"),
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    (Get-Command python -ErrorAction SilentlyContinue).Source
)
foreach ($c in $cands) {
    if ($c -and (Test-Path $c)) { $pyExe = $c; break }
}
if (-not $pyExe) { Write-Host "  ✗ پایتون یافت نشد!" -ForegroundColor Red; exit 1 }

$venvPy = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "  ساخت .venv با $($pyExe) …"
    & $pyExe -m venv (Join-Path $backend ".venv")
}
if (-not (Test-Path $venvPy)) { Write-Host "  ✗ ساخت venv ناموفق" -ForegroundColor Red; exit 1 }
Write-Host "  پایتون بک‌اند: $venvPy" -ForegroundColor Gray

# مارکر وابستگی بر اساس هش requirements.txt — تغییر فایل ⇒ نصب خودکار دوباره
$reqHash = ""
try { $reqHash = (Get-FileHash (Join-Path $backend "requirements.txt") -Algorithm MD5).Hash.Substring(0,8) } catch {}
$marker = Join-Path $backend ".venv\.deps_ok_$reqHash"
$needInstall = -not (Test-Path $marker)
if ($needInstall) {
    Remove-Item (Join-Path $backend ".venv\.deps_ok*") -Force -ErrorAction SilentlyContinue
    Write-Host "  نصب وابستگی‌ها (requirements.txt) …"
    & $venvPy -m pip install --upgrade pip -q
    & $venvPy -m pip install -r (Join-Path $backend "requirements.txt") -q
    if ($LASTEXITCODE -eq 0) { New-Item -ItemType File -Path $marker -Force | Out-Null }
    else { Write-Host "  ⚠ نصب با خطا مواجه شد — لاگ بالا را بررسی کن" -ForegroundColor Yellow }
} else {
    Write-Host "  وابستگی‌ها به‌روز و نصب‌اند (هش requirements: $reqHash)" -ForegroundColor Gray
}

# ---------- [۳] مهاجرت پایگاه‌داده ----------
if ($Prod) {
    Write-Host ""
    Write-Host "=== [۳] مهاجرت‌ها: در حالت -Prod داخل کانتینر اجرا می‌شود (گام ۶) — رد شد ===" -ForegroundColor Gray
} else {
    Write-Host ""
    Write-Host "=== [۳] مهاجرت‌های پایگاه‌داده (Alembic) ===" -ForegroundColor Yellow
    Push-Location $backend
    & $venvPy -m alembic upgrade head
    Pop-Location
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ⚠ مهاجرت ناموفق — اگر Postgres روشن نیست ابتدا اجرا کن: docker-compose up -d db" -ForegroundColor Yellow
    }
}

# ---------- [۴] فرانت‌اند ----------
Write-Host ""
Write-Host "=== [۴] آماده‌سازی فرانت‌اند ===" -ForegroundColor Yellow
$nodeCmd = $null
if (Test-Path (Join-Path $root "tools\node\node.exe")) { $nodeCmd = Join-Path $root "tools\node\node.exe" }
elseif (Test-Path (Join-Path $root "tools\node\node-v24-x64\node.exe")) { $nodeCmd = Join-Path $root "tools\node\node-v24-x64\node.exe" }
else { $nodeCmd = (Get-Command node -ErrorAction SilentlyContinue).Source }
if (-not $nodeCmd) { Write-Host "  ✗ Node یافت نشد (tools\node یا PATH)" -ForegroundColor Red; exit 1 }
$npmCmd = $nodeCmd.Replace("node.exe", "npm.cmd")
if (-not (Test-Path $npmCmd)) { $npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source }
Write-Host "  Node: $nodeCmd" -ForegroundColor Gray

if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "  نصب node_modules …"
    Push-Location $frontend; & $npmCmd install --no-audit --no-fund; Pop-Location
}
# ساخت نسخهٔ نهایی (پوشهٔ dist) — همان چیزی که بک‌اند/سرور سرو می‌کند
Write-Host "  ساخت نسخهٔ نهایی (vite build) …"
Push-Location $frontend
& $npmCmd run build
Pop-Location
if ($LASTEXITCODE -ne 0) { Write-Host "  ⚠ build ناموفق — ادامه می‌دهیم (نسخهٔ قبلی dist باقی می‌ماند)" -ForegroundColor Yellow }

# ---------- [۵] توقف اجراهای قبلی ----------
Write-Host ""
Write-Host "=== [۵] توقف اجراهای قبلی ===" -ForegroundColor Yellow
Get-Process -Name "python*" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "$backend*" } |
    ForEach-Object { Write-Host "  توقف $($_.Id)"; Stop-Process -Id $_.Id -Force }
Get-NetTCPConnection -LocalPort 8000,5173,8880 -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } catch {} }

# ---------- [۶] اجرا ----------
if ($Prod) {
    Write-Host ""
    Write-Host "=== [۶] اجرای PRODUCTION (docker-compose.prod.yml) ===" -ForegroundColor Yellow
    $envFile = Join-Path $root ".env.prod"
    if (-not (Test-Path $envFile)) {
        Write-Host "  ✗ .env.prod در ریشهٔ پروژه نیست — حالت prod بدون آن مجاز نیست (secrets fail-fast)." -ForegroundColor Red
        exit 1
    }
    # پورت انتشار از .env.prod (پیش‌فرض 8880)
    $appPort = 8880
    $m = Select-String -Path $envFile -Pattern '^\s*APP_PORT\s*=\s*(\d+)' | Select-Object -First 1
    if ($m) { $appPort = [int]$m.Matches[0].Groups[1].Value }
    # فعال‌سازی پلاک‌خوان با -Ocr → INSTALL_OCR=true در .env.prod (بدون تکرار)
    if ($Ocr) {
        $txt = [System.IO.File]::ReadAllText($envFile)
        if ($txt -match '(?m)^\s*INSTALL_OCR\s*=') {
            $txt = [regex]::Replace($txt, '(?m)^(\s*INSTALL_OCR\s*=).*$', '$1true')
        } else {
            if (-not $txt.EndsWith("`n")) { $txt += "`r`n" }
            $txt += "INSTALL_OCR=true`r`n"
        }
        [System.IO.File]::WriteAllText($envFile, $txt, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "  ✔ پلاک‌خوان فعال شد (INSTALL_OCR=true) — build بک‌اند این بار سنگین‌تر است (torch CPU + EasyOCR)" -ForegroundColor Green
        Write-Host "  ⚠ بار اولِ تست، مدل‌های EasyOCR (~۱۰۰MB) دانلود و روی volume «easyocr» ماندگار می‌شوند" -ForegroundColor Yellow
    }
    # بک‌آپ پیش از ارتقا (اگر اسکریپت بک‌آپ موجود باشد) — بهترین تلاش
    $bak = Join-Path $root "scripts\backup-db.ps1"
    if (Test-Path $bak) {
        Write-Host "  بک‌آپ پایگاه‌داده پیش از ارتقا …" -ForegroundColor Gray
        try { & powershell -NoProfile -ExecutionPolicy Bypass -File $bak 2>$null | Out-Null } catch {}
    }
    docker compose --env-file $envFile -f (Join-Path $root "docker-compose.prod.yml") up -d --build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ✗ docker compose ناموفق — Docker Desktop روشن است؟ لاگ بالا را بررسی کن." -ForegroundColor Red
        if ($appPort -eq 80) {
            Write-Host "    اگر خطا «Bind for 0.0.0.0:80 failed: port is already allocated» بود → پورت ۸۰ سرور اشغال است:" -ForegroundColor Yellow
            Write-Host "      docker ps --format \"table {{.Names}}\t{{.Ports}}\"   ← ببین چه کانتینری پورت ۸۰ را دارد" -ForegroundColor Yellow
            Write-Host "      یا پورت سامانه را عوض کن:  .\scripts\prod-repair.ps1 -Port 8085 -SkipBuild" -ForegroundColor Yellow
        }
        exit 1
    }
    # بررسی سلامت از طریق nginx (مسیر /health به بک‌اند پروکسی می‌شود)
    Write-Host ""
    Write-Host "=== [۹] بررسی سلامت production (پورت $appPort) ===" -ForegroundColor Yellow
    $okP = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 2
        try {
            $r = Invoke-RestMethod -Uri "http://127.0.0.1:$appPort/health/live" -TimeoutSec 3
            if ($r.status -eq "ok") { $okP = $true; break }
        } catch {}
    }
    if ($appPort -eq 80) { $outUrl = "http://192.168.100.2" } else { $outUrl = "http://192.168.100.2:$appPort" }
    if ($okP) { Write-Host "✔ سامانه در حالت production سالم است." -ForegroundColor Green }
    else {
        Write-Host "⚠ هنوز پاسخ نمی‌دهد — build/مهاجرت ممکن است طول بکشد؛ لاگ را ببین:" -ForegroundColor Yellow
        Write-Host "   docker compose -f docker-compose.prod.yml logs -f backend" -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "  آدرس سامانه:  $outUrl" -ForegroundColor Green
    if ($okP) { exit 0 } else { exit 2 }
}

Write-Host ""
Write-Host "=== [۶] اجرای بک‌اند (uvicorn :8000) ===" -ForegroundColor Yellow
$envFileB = Join-Path $backend ".env"
Start-Process -FilePath $venvPy -ArgumentList "-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000" `
    -WorkingDirectory $backend -WindowStyle Normal

Write-Host "=== [۷] اجرای فرانت‌اند (vite dev :5173) ===" -ForegroundColor Yellow
$nodeDir = Split-Path -Parent $nodeCmd
Start-Process -FilePath "$env:ComSpec" -ArgumentList "/k", "`"$npmCmd`" run dev" `
    -WorkingDirectory $frontend

if (-not $SkipAgent) {
    Write-Host "=== [۸] اجرای گیت‌ایجنت (اگر وجود دارد) ===" -ForegroundColor Yellow
    $agentDir = Join-Path $root "gate-agent"
    if (Test-Path (Join-Path $agentDir "main.py")) {
        Start-Process -FilePath $venvPy -ArgumentList "main.py" -WorkingDirectory $agentDir -WindowStyle Minimized
    } else {
        Write-Host "  گیت‌ایجنت یافت نشد — رد شد" -ForegroundColor Gray
    }
}

# ---------- [۹] سلامت ----------
Write-Host ""
Write-Host "=== [۹] بررسی سلامت (تا ۳۰ ثانیه) ===" -ForegroundColor Yellow
$ok = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/live" -TimeoutSec 3
        if ($r.status -eq "ok") { $ok = $true; break }
    } catch {}
}
if ($ok) {
    Write-Host "✔ بک‌اند سالم است." -ForegroundColor Green
} else {
    Write-Host "⚠ بک‌اند هنوز پاسخ نمی‌دهد — پنجرهٔ uvicorn را بررسی کن (احتمالاً Postgres خاموش است)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  اجرا کامل شد:" -ForegroundColor Green
Write-Host "   • UI:            http://localhost:5173   (dev)"
Write-Host "   • API/Swagger:   http://localhost:8000/api/docs"
Write-Host "   • Health:        http://localhost:8000/health/live"
Write-Host "   • تست پلاک‌خوان: http://localhost:8000/plate-test/"
Write-Host "  توقف: تمام پنجره‌ها را ببند یا .\STOP-SYSTEM.bat" -ForegroundColor Gray
Write-Host "========================================================" -ForegroundColor Cyan
