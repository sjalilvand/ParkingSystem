# گزارش نهایی بسته — سناریوساز و استقرار (۱۴۰۵/۰۷/۱۰)

## محیط‌ها
- D:\ParkingSystem — توسعه + تولید (:8880)
- E:\ParkingSystem — سرور محوطه (داده واقعی ۵۰۷ خودرو) + prod-config آماده

## نسخه
- main: 153cec1
- تگ‌ها: release-v1.0-candidate، release-v1.1

## قابلیت‌های نهایی اضافه‌شده
- سناریوساز: purge انتخابی ۱۴ دسته (ادمین محفوظ) + add-unit/resident/vehicle + setup-default idempotent + summary زنده
- طراح قوانین/تعرفه/قبض/نقشه/باکس — همه متصل به موتور واقعی
- ماتریس دسترسی گرافیکی + فیلتر منو + کاتالوگ ۲۳ مجوز
- تقویم شمسی گرافیکی
- داده‌های پایه: ۵۳ برند/۱۷۷ مدل/۵۸۹ زیرمدل/۱۵ رنگ/۴۶۳ پلاک

## اقلام معلق (مسئولیت کارفرما)
- D1-D10: تصمیمات سیاستی (docs/pending-decisions.md)
- چاپگر حرارتی، دوربین ANPR، باریر، POS (تجهیز)
- Task Scheduler پشتیبان ۳۰ دقیقه‌ای (اسکریپت آماده)
- تست میدانی با سخت‌افزار واقعی

## دستورات کلیدی
- dev: START-APP.bat یا start-all.ps1
- prod: START-SYSTEM.bat (نیازمند .env.prod)
- تست: .\test.ps1
- backup: scripts/backup-db.ps1
