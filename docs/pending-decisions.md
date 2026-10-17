# تصمیمات سیاستی — وضعیت پیاده‌سازی (v1.0)

> نسخه 1.0: همه تصمیمات D1-D10 در کد اعمال شدند (شاخه feature/d1-d10-policy-decisions).
> هر تصمیم **قابل تغییر در زمان-اجرا** است: پنل مدیریت → تنظیمات (app_settings)
> یا متغیر محیطی (.env) — بدون ری‌استارت سرویس.
> مقدار مؤثر هر سیاست: `GET /api/v1/policy-settings` (مجوز settings.view).

| ID | موضوع | گزینه‌ها | وضعیت اعمال‌شده (پیش‌فرض) | محل اعمال | نحوه تغییر |
|----|-------|---------|--------------------------|-----------|------------|
| D1 | سیاست خروج خودرو با بدهی (§۱۳/§۲۳) | ALLOW / WARN / DENY | **WARN** — اعمال شد (زمان-اجرا) | access_control/service.py + runtime_settings | app_settings کلید `gate_policy` یا env `EXIT_UNPAID_POLICY` |
| D2 | قاعده گردکردن تعرفه | ساعتی رو به بالا / دقیقه‌ای | **HOUR_UP** — اعمال شد (زمان-اجرا) | finance/service.py calculate_amounts | app_settings کلید `tariff_policy.rounding` یا env `TARIFF_ROUNDING` |
| D3 | سقف روزانه در چندروزه | 24H / CALENDAR | **24H** (daily_max × ceil(روز)) — اعمال شد؛ گزینه CALENDAR هم پیاده شد | finance/service.py _apply_daily_cap | app_settings کلید `tariff_policy.day_definition` یا env `TARIFF_DAY_DEFINITION` |
| D4 | تعرفه شب (F11) | فعال / غیرفعال | **غیرفعال** — منطق کامل پیاده + تست شد؛ فعال‌سازی با تنظیم | finance/service.py night_overlap_seconds | app_settings `tariff_policy.night_enabled/night_start_hour/night_end_hour` یا env `NIGHT_TARIFF_ENABLED` |
| D5 | نمونه‌های §۲۳ (۸۰۰ دقیقه=صفر و...) | تأیید / اصلاح | **ماتریس نمونه‌ها مستند شد** (docs/tariff-examples-D5.md) + تست‌های codified — نمونه‌های نیازمند تأیید کارفرما برچسب‌گذاری شدند | tests/unit/test_d2_d3_d4_d7_tariff.py | ویرایش مستند + تست پس از تأیید |
| D6 | نقش‌های دارای هر مجوز | تعیین نقش‌ها | **اعمال شد**: کاتالوگ finance/settings/rules/groups تکمیل؛ GUARD_IN: finance.pay+view؛ سایر نقش‌ها: finance.view؛ finance.manage فقط ADMIN | scripts/seed_rbac.py (MATRIX + ROLES) | اجرای مجدد seed_rbac + پنل نقش‌ها |
| D7 | حداقل مبلغ + مهلت خروج پس از پرداخت | تعیین | **اعمال شد**: MIN_CHARGE_AMOUNT=0 (غیرفعال) + EXIT_GRACE_MINUTES=20 با تسویه خودکار اعتبار پیش‌پرداخت | finance/service.py settle_exit_with_prepaid_credit + access_control exit flow | app_settings `tariff_policy.min_charge_amount/exit_grace_minutes` یا env |
| D8 | برخورد حروف پلاک (س/ص→S، ق/گ→G) (F18) | نگاشت یکتا / حفظ وضعیت | **هر دو پیاده شد**؛ پیش‌فرض MANY_TO_ONE (حفظ وضعیت)؛ UNIQUE آماده + اسکریپت migration پلاک‌ها | app/shared/plate.py + scripts/migrate_plate_letters.py | migration سپس env `PLATE_LETTER_MAPPING=UNIQUE` |
| D9 | ممنوعیت تأیید اصلاحیه توسط درخواست‌دهنده | مسدودسازی / هشدار | **هر دو پیاده شد**؛ پیش‌فرض WARN (ثبت در audit)؛ BLOCK = 409 Conflict | finance/router.py + finance/service.py self_approval_decision | app_settings کلید `finance_policy` یا env `SELF_APPROVAL_POLICY` |
| D10 | تکلیف شارژ VOIDED در گزارش‌های مالی | نمایش جدا / حذف از گزارش | **هر دو پیاده شد**؛ پیش‌فرض SEPARATE — endpoint جدید `/reports/financial-summary` | reports/router.py + finance/service.py summarize_charges_for_report | پارامتر `?voided=EXCLUDE` یا app_settings `report_policy` یا env `VOIDED_REPORT_MODE` |

## لایه‌بندی منبع مقدار سیاست‌ها (اولویت از بالا)

1. جدول `app_settings` (کلید گروه: gate_policy / tariff_policy / finance_policy / report_policy) — از پنل مدیریت
2. متغیر محیطی (.env) — هم‌نام ثابت‌های Settings
3. مقدار پیش‌فرض امن در کد (حفظ رفتار مستند v1.1)

## هشدار D8

تبدیل پلاک‌های موجود از MANY_TO_ONE به UNIQUE برای حروف مبهم (س/ش/ص/ث، ذ/ز/ژ/ض/ظ، ...) از روی
plate_normalized ممکن نیست — اسکریپت migration این پلاک‌ها را از plate_raw بازنرمال می‌کند و
پلاک‌های بدون raw را دست‌نخورده گذاشته و گزارش می‌دهد. قبل از اجرا حتماً backup بگیرید:
`python scripts/migrate_plate_letters.py` (dry-run) سپس `--apply`.
