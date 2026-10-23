# بازنشانی نقشهٔ CAD روی دیتابیس زنده — پس از git pull یک بار اجرا کنید
# جاده‌ها + برچسب ردیف‌ها + نمونهٔ اشغال را جایگزین می‌کند و
# تغییر نام شماره‌ها و وضعیت‌های دستی اپراتور را حفظ می‌کند (--keep-edits)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host '== بازنشانی نقشهٔ CAD (import با --purge --keep-edits) ==' -ForegroundColor Cyan
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T backend python -m scripts.import_cad_spots --purge --keep-edits

if ($LASTEXITCODE -eq 0) {
    Write-Host 'OK — نقشهٔ CAD بازسازی شد: ۵۶ جایگاه + ۶ جاده + ۹ برچسب ردیف (۱۰ جایگاه نمونهٔ اشغال)' -ForegroundColor Green
    Write-Host 'صفحه را در مرورگر رفرش کنید (Ctrl+F5)' -ForegroundColor Yellow
} else {
    Write-Host 'خطا — مطمئن شوید سرویس‌ها بالا هستند: docker compose -f docker-compose.prod.yml --env-file .env.prod ps' -ForegroundColor Red
}
