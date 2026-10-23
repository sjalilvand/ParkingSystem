# راهنمای اتصال Google Sheets (الحاقیه §۴) — قدم‌به‌قدم

هدف: شیت «خودروها» روزانه ساعت ۰۳:۰۰ تهران در سامانه همگام شود — فقط‌خواندنی، بدون تخریب بدهی/محدودیت داخلی.

## گام ۱ — ساخت پروژه و حساب سرویس در Google Cloud (≈۵ دقیقه)

1. به **https://console.cloud.google.com** بروید و با حساب گوگل مجموعه وارد شوید.
2. از بالای صفحه **Select project → New Project**؛ نام: `parking-arkide` → Create.
3. پروژه را انتخاب کنید. از منوی کناری: **APIs & Services → Library**؛
   جست‌وجوی **Google Sheets API** → **Enable**.
4. **APIs & Services → Credentials → + Create Credentials → Service account**.
   * نام: `parking-readonly`
   * نقش (Role): لازم نیست (فقط شیت) — Skip را بزنید → Done.
5. در فهرست Service accounts روی حساب ساخته‌شده کلیک کنید → تب **Keys** →
   **Add key → Create new key → JSON** → Create.
   * یک فایل `.json` دانلود می‌شود — **فقط این فایل را نگه دارید** و ایمیل آن
     (مثل `parking-readonly@parking-arkide.iam.gserviceaccount.com`) را یادداشت کنید.

> ⚠️ امنیت: این فایل معتبرِ ورود است؛ به هیچ‌کس ندهید و در مخزن کامیت نکنید
> (در `.gitignore` پوشهٔ `secrets/` رزرو شده است).

## گام ۲ — اشتراک‌گذاری شیت با حساب سرویس (فقط‌خواندنی)

1. شیت خودروها را باز کنید:
   `https://docs.google.com/spreadsheets/d/1ZbiQl_9nab-CH0uR1i9dq6pevcCvY0SfyUuxpIyEjQQ`
2. دکمهٔ **Share** → ایمیل حساب سرویس (گام ۱-۵) را وارد کنید → نقش **Viewer** → Send.
3. نام دقیق تب (worksheet) را یادداشت کنید (پیش‌فرض سامانه: «خودروها»).

## گام ۳ — ستون‌های استاندارد شیت (۲۰ ستون)

سامانه ستون‌ها را با «عنوان سطر اول» می‌شناسد (ترتیب آزاد است؛ ستون ناشناخته نادیده گرفته می‌شود):

```
external_vehicle_id | source_system | plate_raw | plate_normalized |
owner_full_name | owner_mobile | unit_number | tower_code | brand | model |
color | year | vehicle_type | plate_type | permit_type | permit_valid_from |
permit_valid_until | is_active | notes | external_updated_at
```

* الزامی: `external_vehicle_id` + `plate_raw` (پلاک با قالب ایرانی اعتبارسنجی می‌شود: مثل «۱۲ ب ۳۴۵ ایران ۱۱»).
* تاریخ‌ها: میلادی `2026-10-23` یا شمسی `1405-08-01`.
* `is_active`: فعال/غیرفعال یا TRUE/FALSE.

## گام ۴ — نصب خودکار روی سرور (اسکریپت)

فایل JSON حساب سرویس را روی سرور کپی کنید (مثلاً `E:\ParkingSystem\secrets\service-account.json`)
و سپس:

```powershell
cd E:\ParkingSystem
.\scripts\setup-google-sync.ps1 -KeyPath .\secrets\service-account.json -Worksheet "خودروها"
```

اسکریپت خودش: مسیر را در `backend\.env` می‌نویسد، ساختار JSON را اعتبارسنجی می‌کند،
بک‌اند را بالا می‌آورد (اگر پایین است) و **تست اتصال** را صدا می‌زند. خروجی موفق:
نام شیت + فهرست تب‌ها + ایمیل حساب سرویس.

## گام ۵ — اجرا و کنترل

* اجرای دستی: پنل → «همگام‌سازی خودروها (Sheets)» → **تست اتصال** / **Dry-run** / **اجرای همگام‌سازی**.
* اجرای خودکار: روزانه ۰۳:۰۰ تهران (وقتی بک‌اند بالا است) — گزارش در «تاریخچهٔ اجراها».
* صف تعارض: ردیف‌های پلاک نامعتبر/کلید تکراری/مغایرت پلاک اینجا می‌مانند و فقط با تصمیم انسانی (اعمال/رد با یادداشت) تعیین تکلیف می‌شوند.
* گزارش انطباق: همان صفحه — پوشش sync، تعارض باز، آخرین اجرا.

## عیب‌یابی سریع

| خطا | علت/راه‌حل |
|---|---|
| `فایل حساب سرویس خوانده نشد` | مسیر `-KeyPath` اشتباه است |
| `403 PERMISSION_DENIED` | شیت با ایمیل حساب سرویس به‌اشتراک گذاشته نشده (گام ۲) |
| `404 ... RANGE` | نام تب (Worksheet) دقیق نیست — از URL شیت کپی کنید |
| `invalid_grant` | فایل JSON قدیمی/باطل — کلید جدید بسازید (گام ۱-۵) |
| اجرای ۰۳:۰۰ انجام نشد | بک‌اند آن ساعت باید بالا باشد؛ در تاریخچهٔ اجراها و لاگ uvicorn ببینید |
