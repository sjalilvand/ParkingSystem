import math
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access_control.models import ParkingSession
from app.modules.finance.models import Charge, Payment, PaymentAllocation, Tariff

try:  # ZoneInfo در ویندوز بدون tzdata ممکن است موجود نباشد — fallback امن
    from zoneinfo import ZoneInfo
    TEHRAN = ZoneInfo("Asia/Tehran")
except Exception:  # pragma: no cover
    TEHRAN = timezone(timedelta(hours=3, minutes=30))

_NIGHT_MAX_DAYS = 3660  # سقف حلقه شب‌محاسبه (~۱۰ سال) — جلوگیری از حلقه بی‌نهایت


def _as_aware(dt: datetime) -> datetime:
    """تضمین timezone-aware بودن (UTC اگر naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def night_overlap_seconds(
    entry_at: datetime,
    duration_seconds: int,
    night_start_hour: int = 22,
    night_end_hour: int = 6,
    tz=TEHRAN,
) -> int:
    """D4 (F11): مجموع ثانیه‌های همپوشانِ بازه توقف با پنجره شب به وقت محلی تهران.

    پنجره شب روزانه: [night_start_hour:00 امروز → night_end_hour:00 فردا]؛
    اگر شروع < پایان باشد (مثل 2→6) همان روز محاسبه می‌شود.
    """
    if duration_seconds <= 0:
        return 0
    start = _as_aware(entry_at).astimezone(tz)
    end = start + timedelta(seconds=duration_seconds)

    total = 0
    cursor = start.replace(minute=0, second=0, microsecond=0) - timedelta(days=1)
    days = 0
    while cursor < end and days < _NIGHT_MAX_DAYS:
        if night_start_hour <= night_end_hour:
            win_start = cursor.replace(hour=night_start_hour, minute=0, second=0, microsecond=0)
            win_end = cursor.replace(hour=night_end_hour, minute=0, second=0, microsecond=0)
        else:
            win_start = cursor.replace(hour=night_start_hour, minute=0, second=0, microsecond=0)
            win_end = (cursor + timedelta(days=1)).replace(
                hour=night_end_hour, minute=0, second=0, microsecond=0)
        ov_start = max(win_start, start)
        ov_end = min(win_end, end)
        if ov_end > ov_start:
            total += int((ov_end - ov_start).total_seconds())
        cursor += timedelta(days=1)
        days += 1
    return total


def _apply_daily_cap(base: int, tariff, duration_seconds: int, day_definition: str,
                     entry_at: datetime | None, tz, warnings: list) -> int:
    """D3: سقف روزانه در توقف چندروزه — 24H (پیش‌فرض، وضع موجود) یا CALENDAR."""
    if not tariff.daily_max_amount:
        return base
    if day_definition == "CALENDAR" and entry_at is not None:
        start_local = _as_aware(entry_at).astimezone(tz)
        end_local = (start_local + timedelta(seconds=duration_seconds))
        total_days = (end_local.date() - start_local.date()).days + 1
        total_days = max(1, total_days)
    else:
        if day_definition == "CALENDAR" and entry_at is None:
            warnings.append("DAY_DEFINITION_FALLBACK_24H")
        total_days = max(1, _ceil_div(max(0, duration_seconds), 86400))
    cap = tariff.daily_max_amount * total_days
    if base > cap:
        warnings.append("DAILY_CAP_APPLIED")
        return cap
    return base


def calculate_amounts(
    tariff: Tariff | None,
    duration_seconds: int,
    *,
    entry_at: datetime | None = None,
    rounding: str = "HOUR_UP",           # D2: HOUR_UP (وضع موجود) | MINUTE
    day_definition: str = "24H",         # D3: 24H (وضع موجود) | CALENDAR
    night_enabled: bool = False,         # D4: پیش‌فرض خاموش (حفظ رفتار)
    night_start_hour: int = 22,
    night_end_hour: int = 6,
    min_charge_amount: int = 0,          # D7: حداقل مبلغ شارژ (0 = غیرفعال)
    tz=TEHRAN,
) -> dict:
    """محاسبه خالص مبلغ (ریال/BIGINT) — قابل تست واحد.

    سیاست‌های D2/D3/D4/D7 به‌صورت پارامتر هستند؛ لایه سرویس (close_session_amounts)
    مقادیر را از runtime_settings (app_settings → env) تامین می‌کند.
    مقادیر پیش‌فرض دقیقاً رفتار قبلی را بازتولید می‌کنند (سازگاری کامل).
    """
    if duration_seconds is None or duration_seconds < 0:
        duration_seconds = 0
    if tariff is None:
        return {"base": 0, "penalty": 0, "discount": 0, "final": 0, "warnings": ["NO_ACTIVE_TARIFF"]}

    free_seconds = (tariff.free_minutes or 0) * 60
    billable = max(0, duration_seconds - free_seconds)
    if billable == 0:
        return {"base": 0, "penalty": 0, "discount": 0, "final": 0, "warnings": []}

    warnings: list = []
    hourly = tariff.hourly_amount or 0

    # --- D4: تفکیک شب/روز در صورت فعال بودن و وجود زمان ورود ---
    night_secs = 0
    if night_enabled and (tariff.night_amount or 0) > 0:
        if entry_at is not None:
            night_secs = night_overlap_seconds(
                entry_at, billable, night_start_hour, night_end_hour, tz)
        else:
            warnings.append("NIGHT_SKIPPED_NO_ENTRY_TIME")
    day_secs = billable - night_secs

    def _cost(seconds: int, rate: int) -> float:
        if seconds <= 0:
            return 0
        if rounding == "MINUTE":   # D2: محاسبه دقیقه‌ای (بدون گرد به ساعت)
            return (seconds / 3600) * rate
        return _ceil_div(seconds, 3600) * rate  # D2 پیش‌فرض: ساعتی رو به بالا

    base = 0.0
    if night_secs > 0:
        base += _cost(night_secs, tariff.night_amount)
        warnings.append("NIGHT_TARIFF_APPLIED")
    base += _cost(day_secs, hourly)
    base = int(round(base))

    # --- D3: سقف روزانه ---
    base = _apply_daily_cap(base, tariff, duration_seconds, day_definition, entry_at, tz, warnings)

    # --- D7: حداقل مبلغ شارژ ---
    if min_charge_amount > 0 and 0 < base < min_charge_amount:
        base = min_charge_amount
        warnings.append("MIN_AMOUNT_APPLIED")

    return {"base": int(base), "penalty": 0, "discount": 0, "final": int(base), "warnings": warnings}


def initial_tariff_status(require_approval: bool) -> str:
    """وضعیت اولیه تعرفه جدید — جریان تصویب §۲۳ (F8)."""
    return "DRAFT" if require_approval else "ACTIVE"


def charge_outstanding(charge: Charge) -> int:
    """مانده واقعی بدهی یک شارژ (F16)."""
    return max(0, int(charge.amount or 0) - int(getattr(charge, "paid_amount", 0) or 0))


def allocate_payment_amounts(unpaid_charges, amount: int) -> tuple[list, int]:
    """تخصیص خالص مبلغ پرداخت بین شارژهای بدهکار به ترتیب داده‌شده (F16).
    خروجی: (list[(charge, allocated)], remaining_credit) — بدون اثر جانبی."""
    remaining = int(amount)
    allocs: list = []
    for c in unpaid_charges:
        if remaining <= 0:
            break
        outstanding = charge_outstanding(c)
        if outstanding <= 0:
            continue
        alloc = min(remaining, outstanding)
        allocs.append((c, alloc))
        remaining -= alloc
    return allocs, remaining


def payment_unallocated_credit(payment: Payment, allocated_sum: int | None = None) -> int:
    """D7: اعتبارِ هنوز تخصیص‌نیافته یک پرداخت (amount - مجموع allocations)."""
    if allocated_sum is None:
        allocated_sum = 0
    return max(0, int(payment.amount or 0) - int(allocated_sum or 0))


def self_approval_decision(policy: str, requested_by: str | None, user_id: str | None) -> tuple[bool, bool]:
    """D9 (§۲۳): تصمیم تأیید اصلاحیه توسط درخواست‌دهنده.

    خروجی: (allowed, self_approval_flag)
      policy=BLOCK و self_approval => allowed=False (لایه router خطا می‌دهد)
      policy=WARN (پیش‌فرض)        => allowed=True با ثبت هشدار در audit
    """
    is_self = bool(requested_by and user_id and str(requested_by) == str(user_id))
    if is_self and (policy or "WARN").upper() == "BLOCK":
        return False, True
    return True, is_self


def summarize_charges_for_report(rows, voided_mode: str = "SEPARATE") -> dict:
    """D10: خلاصه مالی شارژها با تکلیف VOIDED.

    SEPARATE (پیش‌فرض/تصویب‌شده): VOIDED جدا نمایش داده می‌شود و در جمع فعال نیست.
    EXCLUDE: VOIDED کاملاً حذف می‌شود (بخش voided خالی گزارش می‌شود).
    """
    mode = (voided_mode or "SEPARATE").upper()
    mode = mode if mode in ("SEPARATE", "EXCLUDE") else "SEPARATE"
    active_unpaid = active_paid = 0
    active_unpaid_count = active_paid_count = 0
    voided_total = voided_count = 0
    for c in rows:
        status = (getattr(c, "status", "") or "").upper()
        amount = int(getattr(c, "amount", 0) or 0)
        paid = int(getattr(c, "paid_amount", 0) or 0)
        if status == "VOIDED":
            voided_count += 1
            voided_total += amount
            continue
        outstanding = max(0, amount - paid)
        if status == "PAID" or outstanding <= 0:
            active_paid += paid if status == "PAID" else amount
            active_paid_count += 1
        else:
            active_unpaid += outstanding
            active_unpaid_count += 1
    result = {
        "voided_mode": mode,
        "active": {
            "unpaid_total": active_unpaid, "unpaid_count": active_unpaid_count,
            "paid_total": active_paid, "paid_count": active_paid_count,
            "grand_total": active_unpaid + active_paid,
        },
    }
    if mode == "SEPARATE":
        result["voided"] = {"total": voided_total, "count": voided_count,
                            "note": "VOIDED — نمایش جدا (D10: SEPARATE)"}
    else:
        result["voided"] = {"total": 0, "count": 0,
                            "note": "VOIDED — حذف از گزارش (D10: EXCLUDE)"}
    return result


async def get_active_tariff(db: AsyncSession, now: datetime) -> Tariff | None:
    result = await db.execute(
        select(Tariff).where(Tariff.status == "ACTIVE").order_by(Tariff.priority.desc(), Tariff.created_at.desc())
    )
    for t in result.scalars().all():
        if t.valid_from and now < t.valid_from:
            continue
        if t.valid_until and now > t.valid_until:
            continue
        return t
    return None


async def resolve_tariff_policy(db: AsyncSession) -> dict:
    """D2/D3/D4/D7: خواندن سیاست‌های تعرفه از app_settings/env (runtime_settings)."""
    from app.core.runtime_settings import resolve_tariff_policy as _resolve
    return await _resolve(db)


async def close_session_amounts(db: AsyncSession, session: ParkingSession) -> dict:
    """بستن مالی نشست: محاسبه مبلغ + ساخت Charge. خروجی شامل warnings.
    سیاست‌های D2/D3/D4/D7 در همین نقطه از تنظیمات زمان-اجرا اعمال می‌شوند."""
    now = datetime.now(timezone.utc)
    duration = max(0, int((now - (_as_aware(session.entry_at) or session.entry_at)).total_seconds()))
    session.duration_seconds = duration
    tariff = await get_active_tariff(db, now)
    policy = await resolve_tariff_policy(db)
    amounts = calculate_amounts(
        tariff, duration,
        entry_at=session.entry_at,
        rounding=policy["rounding"],
        day_definition=policy["day_definition"],
        night_enabled=policy["night_enabled"],
        night_start_hour=policy["night_start_hour"],
        night_end_hour=policy["night_end_hour"],
        min_charge_amount=policy["min_charge_amount"],
    )
    session.tariff_id = tariff.id if tariff else None
    session.base_amount = amounts["base"]
    session.penalty_amount = amounts["penalty"]
    session.discount_amount = amounts["discount"]
    session.final_amount = amounts["final"]
    if amounts["final"] > 0:
        db.add(Charge(
            parking_session_id=session.id, charge_type="PARKING",
            amount=amounts["final"],
            description=f"PARKING {duration}s tariff={tariff.title if tariff else '-'}",
        ))
    return amounts


async def settle_exit_with_prepaid_credit(
    db: AsyncSession,
    session: ParkingSession,
    now: datetime,
    grace_minutes: int,
) -> dict | None:
    """D7 (§۲۳): مهلت خروج پس از پرداخت.

    پرداخت‌های «همان پلاک» در بازه مهلت (grace_minutes قبل از اکنون) که هنوز
    اعتبار تخصیص‌نیافته دارند، به شارژِ تازه‌سازِ خروج تخصیص می‌یابند؛ در صورت
    پوشش کامل، شارژ و نشست PAID می‌شوند و راننده بدون توقف عبور می‌کند.
    پرداخت‌های قدیمی‌تر از مهلت، خودکار تخصیص نمی‌یابند (نیازمند اقدام اپراتور).
    """
    if grace_minutes <= 0 or session.final_amount <= 0:
        return None
    charge = (await db.execute(
        select(Charge).where(
            Charge.parking_session_id == session.id,
            Charge.status == "UNPAID",
        ).order_by(Charge.created_at.desc())
    )).scalars().first()
    if charge is None or charge_outstanding(charge) <= 0:
        return None

    since = now - timedelta(minutes=grace_minutes)
    plate = session.plate_normalized
    if not plate:
        return None
    payments = (await db.execute(
        select(Payment).where(
            Payment.plate_normalized == plate,
            Payment.payment_status == "COMPLETED",
            Payment.paid_at >= since,
        ).order_by(Payment.paid_at.desc()).limit(20)
    )).scalars().all()
    if not payments:
        return None

    credit_used = 0
    for p in payments:
        allocated_sum = (await db.execute(
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
            .where(PaymentAllocation.payment_id == p.id)
        )).scalar() or 0
        credit = payment_unallocated_credit(p, allocated_sum)
        if credit <= 0:
            continue
        outstanding = charge_outstanding(charge)
        if outstanding <= 0:
            break
        alloc = min(credit, outstanding)
        db.add(PaymentAllocation(payment_id=p.id, charge_id=charge.id, amount=alloc))
        charge.paid_amount = int(charge.paid_amount or 0) + alloc
        credit_used += alloc
    if credit_used <= 0:
        return None

    if charge_outstanding(charge) <= 0:
        charge.status = "PAID"
        session.payment_status = "PAID"
    return {
        "credit_used": credit_used,
        "charge_id": charge.id,
        "settled": charge.status == "PAID",
        "grace_minutes": grace_minutes,
    }
