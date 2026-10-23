"""الحاقیه §۴ — سرویس همگام‌سازی روزانهٔ خودروها از Google Sheets.

قواعد کلیدی (مطابق الحاقیه):
  * کلید تطبیق = source_system + external_vehicle_id (یکتا)
  * اعتبارسنجی پلاک (قالب ایرانی) و تاریخ‌ها (میلادی ISO یا شمسی)
  * صف تعارض: هر ردیف مشکل‌دار/مبهم به VehicleSyncConflict می‌رود
  * غیرتخریبی: فقط فیلدهای مجاز خودرو؛ بدهی/محدودیت داخلی/سابقه دست نمی‌خورد
  * اجرا: روزانه ۰۳:۰۰ تهران (زمان‌بند در app.main) + اجرای دستی از پنل
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import settings
from app.shared.plate import normalize_plate

# ---------------------------------------------------------------------------
# نگاشت ۲۰ ستونی شیت «خودروها» → فیلدهای سامانه
# ترتیب ستون‌ها مرجع است؛ خواندن شیت با «عنوان ستون» انجام می‌شود و اگر عنوان
# یافت نشد به ترتیب بالا fallback می‌کند.
# ---------------------------------------------------------------------------
SHEET_COLUMNS: list[str] = [
    "external_vehicle_id",     # 1  شناسهٔ خودرو در سیستم مبدأ (کلید)
    "source_system",           # 2  نام سیستم مبدأ (پیش‌فرض OPS)
    "plate_raw",               # 3  متن پلاک (الزامی، اعتبارسنجی قالب ایرانی)
    "plate_normalized",        # 4  نرمال‌شده (اختیاری — اگر خالی از plate_raw ساخته می‌شود)
    "owner_full_name",         # 5  نام مالک
    "owner_mobile",            # 6  موبایل مالک
    "unit_number",             # 7  شمارهٔ واحد
    "tower_code",              # 8  کد برج
    "brand",                   # 9  برند
    "model",                   # 10 مدل
    "color",                   # 11 رنگ
    "year",                    # 12 سال ساخت
    "vehicle_type",            # 13 CAR | MOTORCYCLE | VAN | ...
    "plate_type",              # 14 PERSONAL | GOVERNMENT | TAXI | ...
    "permit_type",             # 15 PERMANENT | GUEST | SECONDARY (اختیاری)
    "permit_valid_from",       # 16 تاریخ شروع مجوز (ISO یا شمسی)
    "permit_valid_until",      # 17 تاریخ پایان مجوز (ISO یا شمسی)
    "is_active",               # 18 فعال (TRUE/FALSE/1/0/فعال/غیرفعال)
    "notes",                   # 19 یادداشت
    "external_updated_at",     # 20 آخرین به‌روزرسانی در مبدأ
]

# فیلدهایی که sync هرگز نمی‌تواند تغییر دهد (محافظت غیرتخریبی)
PROTECTED_FIELDS_NOTE = (
    "charges/payments/بدهی، vehicle_restrictions، used_entries/max_entries مجوزهای "
    "داخلی و سابقهٔ تردد خارج از دامنهٔ sync هستند و هیچ‌گاه تغییر نمی‌کنند."
)

_TRUE_SET = {"true", "1", "yes", "y", "فعال", "بله", "true."}
_FALSE_SET = {"false", "0", "no", "n", "غیرفعال", "خیر"}


def parse_any_date(value: Any) -> datetime | None | str:
    """تاریخ ISO میلادی یا شمسی (yyyy-mm-dd / yyyy/mm/dd) → datetime UTC.

    خروجی: datetime معتبر | None (خالی) | str پیام خطا
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("none", "null", "-"):
        return None
    s = s.replace("‌", "").strip()
    parts = s.replace("/", "-").split("-")
    if len(parts) != 3:
        return f"قالب تاریخ نامعتبر: {s}"
    try:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return f"تاریخ عددی نیست: {s}"
    if y > 1900:  # میلادی
        try:
            return datetime(y, m, d, tzinfo=timezone.utc)
        except ValueError:
            return f"تاریخ میلادی نامعتبر: {s}"
    # شمسی → میلادی (الگوریتم استاندارد جلالی)
    g = _jalali_to_gregorian(y, m, d)
    return datetime(g[0], g[1], g[2], tzinfo=timezone.utc)


def _jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """تبدیل شمسی→میلادی (الگوریتم استاندارد جلالی)."""
    jy += 1595
    days = (-355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
            + ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186))
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        gy += 100 * ((days - 1) // 36524)
        days = (days - 1) % 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)
    sal_a = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    for i in range(1, 13):
        if gd <= sal_a[i]:
            gm = i
            break
        gd -= sal_a[i]
    return gy, gm, gd


def parse_bool(value: Any, default: bool = True) -> bool:
    s = str(value).strip().lower() if value is not None else ""
    if s in _TRUE_SET:
        return True
    if s in _FALSE_SET:
        return False
    return default


def validate_row(rec: dict) -> list[str]:
    """اعتبارسنجی یک ردیف نگاشت‌شده — فهرست خطاها (خالی = معتبر)."""
    errors: list[str] = []
    if not str(rec.get("external_vehicle_id") or "").strip():
        errors.append("MISSING_REQUIRED:external_vehicle_id")
    if not str(rec.get("plate_raw") or "").strip():
        errors.append("MISSING_REQUIRED:plate_raw")
    else:
        if normalize_plate(rec.get("plate_raw")) is None:
            errors.append("INVALID_PLATE")
    for f in ("permit_valid_from", "permit_valid_until"):
        v = rec.get(f)
        if v not in (None, ""):
            r = parse_any_date(v)
            if isinstance(r, str):
                errors.append(f"INVALID_DATE:{f}")
    return errors


def rows_to_records(headers: list[str], rows: list[list]) -> list[dict]:
    """تبدیل ردیف‌های خام به دیکشنری با کلیدهای SHEET_COLUMNS.

    اولویت: تطبیق عنوان ستون؛ در نبود آن، ترتیب SHEET_COLUMNS.
    """
    hmap = {h.strip(): i for i, h in enumerate(headers) if h}
    records: list[dict] = []
    for row in rows:
        rec: dict[str, Any] = {}
        for i, col in enumerate(SHEET_COLUMNS):
            idx = hmap.get(col, i if i < len(row) else -1)
            if 0 <= idx < len(row):
                v = row[idx]
                rec[col] = "" if v is None else (v if not isinstance(v, str) else v.strip())
        records.append(rec)
    return records


class VehicleSyncService:
    """اجرای یک دورهٔ sync کامل (فقط‌خواندنی از گوگل، غیرتخریبی روی DB)."""

    def __init__(self, db: AsyncSession, fetcher=None):
        self.db = db
        self._fetcher = fetcher or _default_fetcher  # تزریق برای تست

    def validate_row_public(self, rec: dict) -> list[str]:
        """نمایش عمومی اعتبارسنجی برای تعیین تکلیف تعارض."""
        return validate_row(rec)

    async def run(self, *, trigger: str = "MANUAL", operator_id: str | None = None,
                  dry_run: bool = False) -> dict:
        from app.modules.vehicle_sync.models import VehicleSyncRun

        run = VehicleSyncRun(trigger=trigger, status="RUNNING",
                             started_at=datetime.now(timezone.utc),
                             spreadsheet_id=settings.GOOGLE_SHEETS_SPREADSHEET_ID,
                             worksheet=settings.GOOGLE_SHEETS_WORKSHEET)
        if not dry_run:
            self.db.add(run)
            await self.db.flush()
        stats: dict[str, Any] = {"rows_total": 0, "rows_valid": 0, "rows_created": 0,
                                 "rows_updated": 0, "rows_skipped": 0, "conflicts": 0,
                                 "invalid_plates": 0, "invalid_dates": 0}
        try:
            data = await self._fetcher()
            headers, rows = data.get("headers", []), data.get("rows", [])
            records = rows_to_records(headers, rows)
            seen_keys: set[tuple[str, str]] = set()
            for n, rec in enumerate(records, start=2):  # ردیف ۲ = اولین داده
                if n - 1 > settings.VEHICLE_SYNC_MAX_ROWS:
                    break
                stats["rows_total"] = n - 1
                key = (str(rec.get("source_system") or "OPS").strip(),
                       str(rec.get("external_vehicle_id") or "").strip())
                errs = validate_row(rec)
                if errs:
                    stats["conflicts"] += 1
                    for e in errs:
                        if e.startswith("INVALID_PLATE"):
                            stats["invalid_plates"] += 1
                        elif e.startswith("INVALID_DATE"):
                            stats["invalid_dates"] += 1
                    await self._add_conflict(
                        run.id if not dry_run else None, n, key, rec, None,
                        "INVALID_PLATE" if any(e.startswith("INVALID_PLATE") for e in errs)
                        else "ROW_ERROR", "؛ ".join(errs), dry_run=dry_run)
                    continue
                if key in seen_keys or not key[1]:
                    stats["conflicts"] += 1
                    await self._add_conflict(run.id if not dry_run else None, n, key, rec,
                                             None, "DUPLICATE_KEY",
                                             "کلید تکراری در شیت", dry_run=dry_run)
                    continue
                seen_keys.add(key)
                result = await self._upsert_vehicle(rec, key, run.id if not dry_run else None,
                                                    n, dry_run=dry_run)
                stats[f"rows_{result}"] = stats.get(f"rows_{result}", 0) + 1
            run.rows_total = stats["rows_total"]
            run.rows_valid = stats["rows_valid"]
            run.rows_created = stats["rows_created"]
            run.rows_updated = stats["rows_updated"]
            run.rows_skipped = stats["rows_skipped"]
            run.conflicts_count = stats["conflicts"]
            run.stats = stats
            run.status = "SUCCESS" if stats["conflicts"] == 0 else "PARTIAL"
            run.finished_at = datetime.now(timezone.utc)
            if not dry_run:
                if operator_id:
                    await write_audit(self.db, user_id=operator_id,
                                      action="VEHICLE_SYNC_RUN", module="vehicle_sync",
                                      entity_type="vehicle_sync_run", entity_id=run.id,
                                      new_values=stats)
                await self.db.commit()
            return {"run_id": run.id if not dry_run else None,
                    "status": run.status, "stats": stats,
                    "protected": PROTECTED_FIELDS_NOTE}
        except Exception as exc:  # noqa: BLE001
            run.status = "FAILED"
            run.error = f"{type(exc).__name__}: {exc}"
            run.finished_at = datetime.now(timezone.utc)
            if not dry_run:
                await self.db.commit()
            return {"run_id": run.id if not dry_run else None,
                    "status": "FAILED", "error": run.error}

    # ------------------------------------------------------------------
    async def _add_conflict(self, run_id, row_number, key, rec, current, ctype,
                            message, dry_run=False):
        from app.modules.vehicle_sync.models import VehicleSyncConflict
        c = VehicleSyncConflict(
            run_id=run_id, row_number=row_number,
            external_vehicle_id=key[1] if key else None,
            source_system=key[0] if key else None,
            conflict_type=ctype, message=message,
            incoming=rec, current=current, status="PENDING")
        if not dry_run:
            self.db.add(c)
            await self.db.flush()

    async def _upsert_vehicle(self, rec, key, run_id, row_number, dry_run=False) -> str:
        """ساخت/به‌روزرسانی فقط فیلدهای مجاز — برخورد با مغایرت → صف تعارض."""
        from app.modules.vehicle_sync.models import VehicleSyncConflict, VehicleExternalRef
        from app.modules.vehicles.models import Vehicle

        source_system, ext_id = key
        ref = (await self.db.execute(
            select(VehicleExternalRef).where(
                VehicleExternalRef.source_system == source_system,
                VehicleExternalRef.external_vehicle_id == ext_id))).scalar_one_or_none()

        norm = rec.get("plate_normalized") or normalize_plate(rec.get("plate_raw"))
        if ref is None:
            # پلاک تکراری در سامانه؟ → تعارض برای تصمیم انسانی (نه ادغام خودکار)
            existing_plate = (await self.db.execute(
                select(Vehicle).where(Vehicle.plate_normalized == norm))).scalars().first()
            if existing_plate is not None:
                await self._add_conflict(
                    run_id, row_number, key, rec,
                    {"vehicle_id": existing_plate.id, "plate_raw": existing_plate.plate_raw},
                    "PLATE_MISMATCH",
                    "این پلاک در سامانه با شناسهٔ دیگری ثبت شده — ادغام نیازمند تأیید انسانی است",
                    dry_run=dry_run)
                return "skipped"
            if dry_run:
                return "created"
            vehicle = Vehicle(
                plate_raw=rec.get("plate_raw"), plate_normalized=norm,
                brand=rec.get("brand") or None, model=rec.get("model") or None,
                color=rec.get("color") or None,
                year=int(rec["year"]) if str(rec.get("year") or "").strip().isdigit() else None,
                vehicle_type=(rec.get("vehicle_type") or "CAR").upper() or "CAR",
                plate_type=(rec.get("plate_type") or "PERSONAL").upper() or "PERSONAL",
                is_active=parse_bool(rec.get("is_active"), True),
                notes=f"[SYNC:{source_system}:{ext_id}] {rec.get('notes') or ''}".strip(),
            )
            self.db.add(vehicle)
            await self.db.flush()
            self.db.add(VehicleExternalRef(
                vehicle_id=vehicle.id, source_system=source_system,
                external_vehicle_id=ext_id,
                external_updated_at=parse_any_date(rec.get("external_updated_at"))))
            await self._maybe_permit(vehicle, rec, run_id, dry_run=dry_run)
            return "created"

        # موجود — به‌روزرسانی فقط فیلدهای مجاز (بدون تخریب)
        vehicle = await self.db.get(Vehicle, ref.vehicle_id)
        if vehicle is None:
            await self._add_conflict(run_id, row_number, key, rec, None, "ROW_ERROR",
                                     "ارجاع خارجی به خودروی حذف‌شده", dry_run=dry_run)
            return "skipped"
        if vehicle.plate_normalized != norm:
            await self._add_conflict(
                run_id, row_number, key, rec,
                {"vehicle_id": vehicle.id, "plate_raw": vehicle.plate_raw},
                "PLATE_MISMATCH", "پلاک مبدأ با پلاک سامانه متفاوت است",
                dry_run=dry_run)
            return "skipped"
        if dry_run:
            return "updated"
        changed = False
        for f in ("brand", "model", "color"):
            v = rec.get(f) or None
            if v and getattr(vehicle, f) != v:
                setattr(vehicle, f, v)
                changed = True
        if str(rec.get("year") or "").strip().isdigit() and int(rec["year"]) != vehicle.year:
            vehicle.year = int(rec["year"])
            changed = True
        new_active = parse_bool(rec.get("is_active"), vehicle.is_active)
        if new_active != vehicle.is_active:
            vehicle.is_active = new_active
            changed = True
        if changed:
            ref.external_updated_at = parse_any_date(rec.get("external_updated_at"))
        await self._maybe_permit(vehicle, rec, run_id, dry_run=dry_run)
        return "updated"

    async def _maybe_permit(self, vehicle, rec, run_id=None, dry_run=False) -> None:
        """مجوز فقط برای خودروی تازه‌وارد sync ساخته می‌شود؛ تغییر مجوزهای
        موجودِ داخلی ممنوع (محافظت غیرتخریبی) — تغییرات مجوز → صف تعارض."""
        from app.modules.vehicle_sync.models import VehicleSyncConflict
        from app.modules.vehicles.models import AccessPermit

        ptype = (rec.get("permit_type") or "").upper()
        if not ptype:
            return
        existing = (await self.db.execute(
            select(AccessPermit).where(
                AccessPermit.vehicle_id == vehicle.id,
                AccessPermit.status == "ACTIVE"))).scalars().all()
        if existing:
            # تغییر نوع/بازهٔ مجوز موجود = تعارض (نیازمند تأیید انسانی)
            if dry_run:
                return
            self.db.add(VehicleSyncConflict(
                run_id=run_id, row_number=None,
                conflict_type="PERMIT_CHANGE",
                message="ردیف شیت حاوی مجوز است اما خودرو مجوز فعال داخلی دارد — "
                        "مجوز داخلی دست نخورد",
                incoming=rec, current={"permit_type": existing[0].permit_type},
                status="PENDING"))
            await self.db.flush()
            return
        if dry_run:
            return
        vf = parse_any_date(rec.get("permit_valid_from"))
        vu = parse_any_date(rec.get("permit_valid_until"))
        self.db.add(AccessPermit(
            vehicle_id=vehicle.id, plate_normalized=vehicle.plate_normalized,
            permit_type=ptype,
            valid_from=vf if not isinstance(vf, str) else None,
            valid_until=vu if not isinstance(vu, str) else None,
            status="ACTIVE", issued_by=None,
            reason="ایجادشده توسط همگام‌سازی Google Sheets"))


async def _default_fetcher() -> dict:
    from app.modules.vehicle_sync.sheet_client import fetch_sheet_rows
    return await fetch_sheet_rows()
