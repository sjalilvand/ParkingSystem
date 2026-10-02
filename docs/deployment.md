# استقرار و بهره‌برداری — ParkingSystem

## ۱) توسعه (Dev)
    .\start-all.ps1        # infra(docker) + backend:8000 + frontend:5173 + agent:8091
    cd backend; .\.venv\Scripts\Activate.ps1; python -m pytest -q
- ادمین توسعه: admin / Admin@1234 (فقط dev!)
- DB dev: postgres روی 127.0.0.1:15432 (host) — پورت قبلی 56300 در محدوده رزرو Hyper-V بود.

## ۲) تولید (Prod) — پروژه ایزوله parkingsystem-prod
پیش‌نیاز: .env.prod شامل APP_PORT=8880 و secrets قوی (اسکریپت موج۳b در صورت نبود، تولید می‌کند).
سخت‌گیر امنیتی: اگر JWT_SECRET_KEY/APP_SECRET_KEY/GATE_API_KEY پیش‌فرض یا کوتاه باشند، backend بوت نمی‌شود (fail-fast عمدی).
    .\START-SYSTEM.bat      # تشخیص مسیر خودکار (%~dp0) + انتظار سلامت
    .\STATUS.bat  /  .\STOP-SYSTEM.bat
- Web: http://localhost:8880  | Swagger: /api/docs | WS: /ws/v1/events?token=...
- Prod از volumes جدا (parkingsystem-prod_*) و از dev پورت و نام جدا دارد.

## ۳) Migration
    cd backend; .\.venv\Scripts\python.exe -m alembic upgrade head
- هرگز create_all جایگزین migration نیست (درگاه ممیزی: F15).

## ۴) پشتیبان‌گیری/بازیابی (REQ-17)
- دستی: docker exec parking-postgres pg_dump -U parking parking_db > logs\db-backup-<stamp>.sql
- بازیابی: create DB → psql < backup → (در صورت نیاز) alembic stamp/upgrade
- زمان‌بندی ۳۰ دقیقه (REQ-17-01): Task Scheduler → PowerShell فوق + نگهداشت ۴۸ نسخه (پیشنهاد؛ نیازمند ایجاد Scheduled Task — گام بعدی)

## ۵) Rollback
- کد: git revert یا شاخه audit/baseline-20261002-0805
- DB: restore از logs\db-backup-*.sql (فهرست در logs)

## ۶) چک‌لیست بهره‌برداری (§۲۴)
1 استقرار نرم‌افزار ✅ (این سند) 2. مستند معارف ✅ (README+docs) 3. داده پایه داده ✅ (seed scripts) 4. مستند آموزش ⏳ 5. راهنمای کاربران ⏳ 6. ماتریس دسترسی ✅ (matrix) 7. تعرفه/نمونه محاسبه ✅ (preview+tests) 8. پشتیبانی/اظطراری ◐ 9. گزارش پذیرش ✅ (test-report) 10. فهرست تجهیزات ➖ (تأمین مادی) 11. نکهداری/پشتیبانی ⏳ (قرارداد) 12. تحویل مالکیت/آموزش — پس از §۲۳ تصویب D1–D10.
