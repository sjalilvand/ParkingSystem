# سند ممیزی نیازمندی‌ها — ParkingSystem (v0.2)

مرجع: «سند جامع نیازمندی‌ها و طرح اجرایی نسخه ۱٫۰» (docs/parkingSystem.docx)
شاخه: p0-wave1-fixes | کامیت‌ها: ef9a2b7، cca1468، 1c74fe4، d3d788f، 1d3638c (+wave2b)
پشتیبان‌ها: logs/db-backup-*.sql | Alembic head: p0002_finance_paid_amount

## یافته‌ها و وضعیت

| ID | شدت | ارجاع سند | شرح | اصلاح | وضعیت |
|----|-----|-----------|-----|-------|-------|
| F1 | P0 | §۸ | عملیات دستی گیت/راهبند بدون مجوز API | مجوز + کلید ENFORCE_GATE_PERMISSIONS | ✅ موج۱ |
| F2 | P0 | §۴/§۱۱ | چند نشست OPEN برای یک پلاک | ایندکس یکتای جزئی + CLOSED_ANOMALY | ✅ موج۱ (p0001) |
| F3 | P0 | §۴/ح/§۱۴ | تداخل همزمان کلیدهای یکتا → 500 | IntegrityError → duplicate | ✅ موج۱+۲a |
| F4 | P0 | §۱۱ | تخصیص فضا بدون قفل | with_for_update + بررسی FREE | ✅ موج۱ (اتمیک کامل: موج۳) |
| F5 | P0 | §۱۳/§۲۳ | خروج با بدهی بدون سیاست | EXIT_UNPAID_POLICY (پیش‌فرض WARN) | ✅ (تصویب D1) |
| F6 | P0 | §۵/§۷ | prod با secrets پیش‌فرض | fail-fast | ✅ موج۱ |
| F7 | P1 | §۷ | مقایسه کلید گیت | compare_digest | ✅ موج۱ |
| F8 | P0 | §۲۳ | تعرفه بدون تصویب/چند فعال | DRAFT→ACTIVATE انحصاری + preview + audit | ✅ موج۲a (p0002) |
| F9 | P0 | §۸ | APIها فقط احراز هویت | gate/finance/violations/parking مجزدار + کاتالوگ مجوز | ✅ موج۲a/2b (فهرست نقش‌ها: D6) |
| F10 | P1 | §۴ | ~~max_entries اعمال نمی‌شود~~ | **فرضیه رد شد** — شاهد: vehicles/service.py::permit_entries_available در find_active_permit | ✅ بی‌نیاز |
| F11 | P2 | §۲۳ | night_amount بلااستفاده | — | 📋 D4 |
| F12 | P1 | — | dev/prod هم‌نام و هم‌volume | — | ⏳ موج۳ |
| F13 | P0 | — | migration خراب کامیت‌شده | تعمیر | ✅ موج۱ |
| F14 | P1 | §۱۱ | ورود همزمان پلاک با رویداد متمایز → 500 | — | ⏳ |
| F15 | P0 | — | DB بدون alembic_version (create_all) | stamp + upgrade | ✅ |
| F16 | P0 مالی | §۱۴ | پرداخت جزئی = بدهی کامل باقی (پرداخت تکراری) | charges.paid_amount + debts بر مبنای مانده | ✅ موج۲a |
| F17 | P1 | §۱۱ | تخصیص بدون اعتبارسنجی | اعتبارسنجی کامل + قفل + audit | ✅ موج۲b |
| F18 | P2 | §۴ | برخورد حروف نرمال‌سازی (س/ص→S...) | تغییر داده‌شکن ممنوع | 📋 D8 |
| F19 | P0 مالی | §۱۴/§۱۵ | لغو تخلفِ تأییدشده بدهی را باقی می‌گذارد | _void_unpaid_charge (VOIDED) + مسیر اصلاحیه برای پرداخت‌شده | ✅ موج۲b |
| F20 | P1 | §۱۵ | اعتراض بدون اعتبارسنجی/اثر | نتیجه محدود به ACCEPTED/REJECTED + اثر مالی لغو | ✅ موج۲b |
| F21 | P1 | §و | requires_image نادیده | 422 REQUIRED_IMAGE_MISSING | ✅ موج۲b |
| F22 | P1 | §۴/§ح | آفلاین بدون max_entries | بررسی در offline_decide (محافظه‌کارانه) | ✅ موج۲b |
| F23 | P2 | §۴ | used_entries++ در ورود تکراری | — | ⏳ موج۳ |

## آزمون‌ها (واقعاً اجراشده)
- موج۲b: 63 passed (بک‌اند) + 4/4 agent decision (importlib) + E2E smoke تخلف (422 بدون تصویر → ثبت → confirm→UNPAID → cancel→VOIDED)
- موج‌های قبل: 43 → 56 passed

## محدودیت‌های شناخته‌شده
- سقف ورود در قطعی طولانی: snapshot قدیمی است؛ سقف پرشده فقط «بررسی» می‌خواهد نه عبور (محافظه‌کارانه، §ح)
- تست‌های integration با DB واقعی و هم‌زمانی موازی: موج۳
| F24 | P0 مالی | §۱۴ | create_payment: flush قبل از try، تداخل همزمان reference → 500 | کل عملیات پرداخت درون try/catch IntegrityError → duplicate | ✅ موج۳a (تست integration همزمانی) |

## زیرساخت تست (درس ممیزی)
- تستهای integration روی Postgres واقعی ایزوله (parking_test_db) با یک event loop پایدار اجرا میشوند؛ علت اولیه شکستهای ناپایدار، تداخل event loop بود (باگ محیط تست، نه اپ).
