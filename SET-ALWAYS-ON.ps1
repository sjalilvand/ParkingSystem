# ============================================================================
#  SET-ALWAYS-ON.ps1 — ParkingSystem (برج‌های ارکیده)
#  سرور پارکینگ هرگز به خواب/استندبای/هایبرنیت نمی‌رود.
#
#  ریشهٔ «وقتی مدتی با سیستم کار نکنی میره تو حالت استپ و استپ میشه»:
#  ویندوز بعد از چند دقیقه بی‌کاری به استندبای می‌رود و Docker Desktop (و
#  همهٔ سرویس‌ها و دوربین‌ها) با آن منجمد می‌شود — تا وقتی کسی موس تکان
#  ندهد هیچ پلاکی خوانده نمی‌شود. این اسکریپت آن را یک‌بار برای همیشه
#  خاموش می‌کند (idempotent — اجرای مکرر مشکلی ندارد).
#
#  اجرا:  PowerShell:  .\SET-ALWAYS-ON.ps1     (بار اول با دسترسی Administrator)
# ============================================================================

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=== SET-ALWAYS-ON — خاموش‌کردن خواب ویندوز ===" -ForegroundColor Cyan

# ۱) استندبای/خواب — هرگز (برق شهری و باتری)
powercfg /change standby-timeout-ac 0 | Out-Null
powercfg /change standby-timeout-dc 0 | Out-Null
# ۲) هایبرنیت — هرگز
powercfg /change hibernate-timeout-ac 0 | Out-Null
powercfg /change hibernate-timeout-dc 0 | Out-Null
# ۳) دیسک — هرگز به خواب نرود (قطع‌وصلیِ DB/MinIO می‌سازد)
powercfg /change disk-timeout-ac 0 | Out-Null
# ۴) نمایشگر — خاموش نشود (پنل گیت باید همیشه رو باشد؛ پلاک‌خوانی روی
#    سرور است و به نمایشگر وابسته نیست، ولی «صفحهٔ بی‌وقفه» همین است)
powercfg /change monitor-timeout-ac 0 | Out-Null
# ۵) هایبرنیت کلاً غیرفعال (حذف hiberfil) — اختیاری؛ اگر نشد بی‌اهمیت است
try { powercfg /hibernate off 2>$null | Out-Null } catch {}

# ۶) خواب‌شدن tabهای Edge (Sleeping Tabs) خاموش شود — صفحهٔ گیت تا ابد بیدار
#    (به‌علاوه خود صفحهٔ گیت با «بیدارماندن صفحه» هم محافظت شده است)
try {
    $edge = "HKLM:\SOFTWARE\Policies\Microsoft\Edge"
    if (-not (Test-Path $edge)) { New-Item -Path $edge -Force | Out-Null }
    Set-ItemProperty -Path $edge -Name SleepingTabsEnabled -Value 0 -Type DWord -ErrorAction SilentlyContinue
    Write-Host "  ✔ خواب‌شدن tabهای Edge (Sleeping Tabs) خاموش شد" -ForegroundColor Green
} catch {
    Write-Host "  ⚠ تنظیم Edge اعمال نشد (دسترسی Administrator لازم است) — چندان مهم نیست؛ صفحهٔ گیت خودش محافظت شده" -ForegroundColor Yellow
}

# ---- تأیید ----
Write-Host ""
Write-Host "تنظیمات جاری (برق شهری — مقدار 0 یعنی هرگز):" -ForegroundColor Gray
try {
    $out = powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 2>$null | Select-String "Current AC"
    if ($out) { Write-Host "  استندبای: $($out.ToString().Split(':')[-1].Trim())" }
    $out2 = powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE 2>$null | Select-String "Current AC"
    if ($out2) { Write-Host "  خاموشی نمایشگر: $($out2.ToString().Split(':')[-1].Trim())" }
    $out3 = powercfg /query SCHEME_CURRENT SUB_DISK DISKIDLE 2>$null | Select-String "Current AC"
    if ($out3) { Write-Host "  خواب دیسک: $($out3.ToString().Split(':')[-1].Trim())" }
} catch {}

Write-Host ""
Write-Host "✔ سرور از این به بعد تا ابد بیدار می‌ماند — حتی وقتی هیچ‌کس با آن کار نمی‌کند." -ForegroundColor Green
Write-Host "  (پلاک‌خوانی داخل Docker است و به بوت‌بودن ویندوز وابسته است؛" -ForegroundColor Gray
Write-Host "   فقط مطمئن شوید Docker Desktop در Startup ویندوز فعال است.)" -ForegroundColor Gray
