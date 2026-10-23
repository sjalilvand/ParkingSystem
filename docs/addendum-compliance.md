# انطباق الحاقیه (۵ محور) — سند تکمیلی تحویل

این سند «الحاقیه» درخواست کارفرما را به اقلام پیاده‌شده، مدرک آزمون و
گام‌های باقی‌ماندهٔ میدانی نگاشت می‌کند. ماتریس کامل ۲۶ بخش: docs/requirements-matrix.md

---

## محور ۱ — اصلاح ساختار منوها
**خواسته:** تفکیک دو سطح اول «سامانه عملیاتی» / «شبیه‌ساز و آزمون سناریوها» با ساختار درختی دقیق (۱۱ گروه عملیاتی + ۹ گروه شبیه‌ساز)؛ ساده/بزرگ برای گیت.

**تحویل:**
- منوی درختی تاشو در `frontend/src/layouts/MainLayout.tsx` — دو بخش، ۱۱ گروه عملیاتی، ۹ گروه شبیه‌ساز (جدول کامل: docs/menu-structure.md).
- دکمهٔ بزرگ «پنل گیت» پین‌شدهٔ بالای منو برای اپراتور.
- فیلتر مجوز در همهٔ سطوح (گروه خالیِ بی‌مجوز رندر نمی‌شود).
- نسخهٔ UI به ۵.۰ ارتقا یافت (چیپ کنار لوگو).

**مدرک:** build سبز (tsc + vite)؛ صفحهٔ کاتالوگ آزمون میدانی UI با op1/admin.

## محور ۲ — تفکیک واقعی شبیه‌ساز از محیط عملیاتی
**خواسته:** DB/فایل‌ها/صف‌های جدا؛ برچسب «آزمایشی ـ فاقد اعتبار مالی و عملیاتی»؛ موتور قواعد مشترک؛ ۲۰ سناریوی الزامی SIM-01..SIM-20 با پیش‌شرط/مراحل/نتیجهٔ مورد انتظار.

**تحویل:**
- `backend/app/db/sim_session.py`: موتور/فکتوری جدا (`SIM_DATABASE_URL`، پیش‌فرض SQLite محلی `sim_parking.db`) + گارد fail-fast `SIM_STRICT` (برابری با DB عملیاتی ممنوع) + `ensure_sim_schema` idempotent.
- ماژول‌های `simulator` و `scenario` (سناریوساز) کاملاً روی SimSessionLocal سوییچ شدند — purge/seed دیگر هرگز به دادهٔ واقعی دست نمی‌زند.
- برچسب الزامی: `frontend/src/components/SimBanner.tsx` روی هر ۵ صفحهٔ شبیه‌ساز.
- کاتالوگ ۲۰ سناریو: `backend/app/modules/simulator/sim_catalog.py` (پیش‌شرط/مراحل/نتیجهٔ مورد انتظار فارسی) + API `GET/POST /api/v1/simulator/scenarios[/{id}/run]` + صفحهٔ `/sim-scenarios` با داوری خودکار PASS/FAIL و نمایش JSON ردیاب.
- `GET /api/v1/simulator/isolation`: وضعیت جداسازی + آدرس DB شبیه‌ساز (بدون پسورد).
- موتور قواعد و `GateDecisionService` مشترک ماندند؛ فقط داده جدا است (مطابق «موتور قواعد مشترک»).

**مدرک:** `tests/unit/test_sim_isolation.py` (۴ تست: جدایی موتورها، گارد fail-fast، ساخت اسکیما، عدم نشت داده به DB عملیاتی).

## محور ۳ — شناسایی سریع پلاک
**خواسته:** در محدودهٔ زاویه/نور/سرعت تأییدشده (نه هر زاویه)؛ هدف صدک ۹۵ < ۱ ثانیه؛ مسیر تأیید انسانی برای اطمینان پایین/ناشناس («ثبت‌نشده»)؛ حفظ مقدار اصلی + اصلاح‌شده + کاربر.

**تحویل:**
- پاکت ثبت: `backend/app/modules/plate_ocr/envelope.py` — ارزیابی زاویه/نور/سرعت/اطمینان با آستانه‌های زمان‌اجرا از `app_settings` گروه `plate_envelope` (fallback به env). خوانش خارج از پاکت → `NEEDS_REVIEW`.
- قفل ایمنی در `GateDecisionService.process_plate_event`: خوانش کم‌اطمینان/خارج از پاکت هرگز راهبند را خودکار باز نمی‌کند → `REQUIRE_OPERATOR_APPROVAL / ENVELOPE_REVIEW_REQUIRED`.
- نگه‌داشت سابقه: migration `p0006` — ستون‌های `plate_corrected/plate_corrected_normalized/corrected_by/corrected_at/correction_note/review_status/capture_quality/processing_ms` روی `plate_recognition_events`؛ مقدار اصلی هرگز بازنویسی نمی‌شود.
- صف بازبینی: `GET /gate/plate-reviews?status=` + `POST /gate/plate-reviews/{id}/resolve` (CONFIRM/CORRECT/REJECT) + audit خودکار.
- متریک عملکرد: `GET /gate/plate-reviews/metrics` (p50/p95 تأخیر پردازش + هدف ۱۰۰۰ms).
- UI: صفحهٔ «بازبینی پلاک» (`/plate-review`) با جعبه‌پلاک گرافیکی، نشانگر نقض پاکت، دیالوگ اصلاح/تأیید/رد.
- موتور OCR (موج ۹/۱۲): تشخیص+خوانش با بودجهٔ زمانی و fallback کلاسیک — پایهٔ سرعت p95.

**مدرک:** `tests/unit/test_plate_envelope.py` (۳ تست: ارزیابی پاکت، قفل خودکار-بازنشدن، اصلاح با حفظ اصلی+کاربر+زمان).

**میدانی باقی‌مانده:** نصب دوربین ANPR حرفه‌ای و کالیبراسیون آستانه‌ها با نمونهٔ واقعی (پس از Get-Printer/دوربین).

## محور ۴ — همگام‌سازی روزانهٔ Google Sheets
**خواسته:** شیت خودروها (ID: 1ZbiQl_9nab-CH0uR1i9dq6pevcCvY0SfyUuxpIyEjQQ)؛ حساب سرویس فقط‌خواندنی؛ کلید = source_system + external_vehicle_id؛ نگاشت ۲۰ ستون مشخص؛ اعتبارسنجی پلاک/تاریخ؛ صف تعارض؛ اجرای ۰۳:۰۰ تهران + دستی؛ بدون تخریب بدهی/محدودیت داخلی؛ APIهای /integrations/google-sheets و /vehicle-sync/* و /compliance/*.

**تحویل:**
- ماژول `backend/app/modules/vehicle_sync/`:
  - `sheet_client.py`: JWT RS256 (pyjwt+cryptography) → Sheets API v4 فقط‌خواندنی با httpx؛ کش توکن؛ `test_connection`.
  - `service.py`: نگاشت ۲۰ ستونی `SHEET_COLUMNS`، اعتبارسنجی پلاک ایرانی (`shared/plate.normalize_plate`) و تاریخ (ISO میلادی + شمسی با تبدیل استاندارد جلالی)، کلید یکتا، upsert غیرتخریبی (فقط فیلدهای مجاز خودرو؛ مجوز فقط برای خودروی تازه؛ تغییر مجوز موجود → تعارض PERMIT_CHANGE).
  - `models.py` + migration `p0007`: `vehicle_external_refs` (uq روی source_system+external_vehicle_id)، `vehicle_sync_runs`، `vehicle_sync_conflicts`.
  - زمان‌بند: حلقهٔ asyncio در `app/main.py` — روزانه ۰۳:۰۰ Asia/Tehran (`VEHICLE_SYNC_HOUR`) + اجرای دستی؛ خطا فقط لاگ (جریان اصلی نمی‌شکند).
  - API: `GET /integrations/google-sheets/config`، `POST .../test`، `POST .../run[?dry_run=true]`، `GET /vehicle-sync/runs`، `GET /vehicle-sync/conflicts`، `POST /vehicle-sync/conflicts/{id}/resolve`، `GET /compliance/vehicles`.
- UI: صفحهٔ «همگام‌سازی خودروها» (`/vehicle-sync`) — پوشش انطباق، تست اتصال، dry-run، اجرای واقعی، صف تعارض با اعمال/ردِ دارای یادداشت، تاریخچهٔ اجراها.

**راه‌اندازی (یک‌بار):** فایل JSON حساب سرویس فقط‌خواندنی را کنار backend قرار دهید و در `.env`:
```
GOOGLE_SERVICE_ACCOUNT_FILE=./service-account-readonly.json
GOOGLE_SHEETS_SPREADSHEET_ID=1ZbiQl_9nab-CH0uR1i9dq6pevcCvY0SfyUuxpIyEjQQ
GOOGLE_SHEETS_WORKSHEET=خودروها
```
و شیت را با ایمیل حساب سرویس (فقط‌خواننده) به اشتراک بگذارید.

**مدرک:** `tests/unit/test_vehicle_sync.py` (۳ تست: جریان کامل ساخت/تعارض/به‌روزرسانی/PLATE_MISMATCH/PERMIT_CHANGE/غیرتخریبی، تاریخ شمسی، نگاشت عنوان ستون).

## محور ۵ — ماتریس انطباق ۲۶ بخش
**خواسته:** ماتریس ۲۶ بخش سند اصلی (REQ-xxx با مدرک آزمون) + اقلام تحویل تکمیلی.

**تحویل:** `docs/requirements-matrix.md` بازنویسی کامل شد — فهرست ۲۶ بخش (بخش ۰ اصول اجرایی + فصل‌های ۱–۲۴ سند + بخش ۲۵ الحاقیه) با REQ-xxx، نوع، وضعیت و شاهد کد/تست + اقلام تحویل تکمیلی الحاقیه (REQ-A5-01 و REQ-22-13). همین فایل.

## جمع‌بندی وضعیت الحاقیه
| محور | وضعیت | تست |
|---|---|---|
| ۱ منو | ✅ کامل | build سبز + میدانی UI |
| ۲ شبیه‌ساز | ✅ کامل | ۴ تست ایزولاسیون |
| ۳ پلاک‌خوان | ✅ کامل (کالیبراسیون میدانی معلق) | ۳ تست پاکت/اصلاح |
| ۴ Sheets | ✅ کامل (کلید سرویس = تنظیم کارفرما) | ۳ تست sync |
| ۵ ماتریس | ✅ کامل | — |
