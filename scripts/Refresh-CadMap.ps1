# بازنشانی نقشهٔ CAD روی دیتابیس زنده — یک بار پس از git pull
# جاده‌ها + برچسب ردیف‌ها + نمونهٔ اشغال را جایگزین نقشهٔ قبلی می‌کند
# (وضعیت‌های دستیِ قبلی اپراتور جایگزین می‌شوند — نقشه از JSON بازسازی می‌شود)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host '== بازنشانی نقشهٔ CAD (import با --purge) ==' -ForegroundColor Cyan
docker compose --env-file .env.prod exec -T backend python -m scripts.import_cad_spots --purge

if ($LASTEXITCODE -eq 0) {
    Write-Host 'OK — نقشهٔ CAD بازسازی شد: ۵۶ جایگاه + ۶ جاده + ۹ برچسب ردیف (۱۰ جایگاه نمونهٔ اشغال)' -ForegroundColor Green
    Write-Host 'صفحه را در مرورگر رفرش کنید (Ctrl+F5)' -ForegroundColor Yellow
} else {
    Write-Host 'خطا — مطمئن شوید سرویس‌ها بالا هستند: docker compose --env-file .env.prod ps' -ForegroundColor Red
}
