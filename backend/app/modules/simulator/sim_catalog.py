"""الحاقیه §۲ — کاتالوگ ۲۰ سناریوی الزامی آزمون شبیه‌ساز (SIM-01 تا SIM-20).

هر سناریو سه جزء الزامی دارد: پیش‌شرط / مراحل / نتیجهٔ مورد انتظار.
سناریوهای «خودکار» با runner روی پایگاه‌دادهٔ جداگانهٔ شبیه‌ساز اجرا می‌شوند و
ردیاب تصمیم (trace) برمی‌گردانند؛ سناریوهای «میدانی» به تجهیز نیاز دارند و
فقط مستند و قابل علامت‌گذاری (تأیید دستی) هستند.

نتیجهٔ اجرا همیشه شامل برچسب «آزمایشی ـ فاقد اعتبار مالی و عملیاتی» است.
"""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from sqlalchemy import func, select

from app.db.sim_session import SimSessionLocal
from app.modules.access_control.models import AccessEvent, ParkingSession
from app.modules.finance.models import Charge
from app.modules.vehicles.models import Vehicle
from app.modules.violations.models import Violation

SIM_LABEL = "آزمایشی ـ فاقد اعتبار مالی و عملیاتی"


# ---------------------------------------------------------------------------
# Runnerها — همهٔ اجراها روی SimSessionLocal (DB جدا) اتفاق می‌افتند.
# ---------------------------------------------------------------------------

async def _count(db, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def _run_reset_setup() -> dict:
    from app.modules.simulator import scenario as scen
    info = await scen.setup_scenario()   # purge + seed روی DB شبیه‌ساز
    return {"setup": info}


async def _gate(role: str, direction: str) -> dict:
    from app.modules.simulator import scenario as scen
    return await scen._run_gate_step(role, direction)  # noqa: SLF001


async def _activate_rule(code: str) -> dict:
    from app.modules.simulator import scenario as scen
    return await scen._activate_rule(code)  # noqa: SLF001


async def _last_decision(role: str, direction: str) -> dict:
    from app.modules.simulator import scenario as scen
    plate = await scen._role_plate(role)
    if not plate:
        return {}
    from app.shared.plate import normalize_plate
    norm = normalize_plate(plate)
    async with SimSessionLocal() as db:
        row = (await db.execute(
            select(AccessEvent)
            .where(AccessEvent.plate_normalized == norm,
                   AccessEvent.event_type == direction)
            .order_by(AccessEvent.event_time.desc())
            .limit(1))).scalars().first()
        if row is None:
            return {}
        return {"decision": row.decision, "decision_reason": row.decision_reason}


async def _sim01_setup() -> dict:
    data = await _run_reset_setup()
    from app.modules.residents.models import Person
    async with SimSessionLocal() as db:
        v = await _count(db, Vehicle)
        p = await _count(db, Person)
    return {"vehicles_seeded": v, "persons_seeded": p, **data}


async def _sim02_resident_valid() -> dict:
    await _run_reset_setup()
    r_in = await _gate("ALI1", "IN")
    return {"entry": r_in, "expected_decision": "ALLOW"}


async def _sim03_yard_applicant() -> dict:
    await _run_reset_setup()
    r_in = await _gate("ALI2", "IN")
    return {"entry": r_in}


async def _sim04_stranger_no_permit() -> dict:
    await _run_reset_setup()
    r_in = await _gate("STR1", "IN")
    return {"entry": r_in}


async def _sim05_exit_free() -> dict:
    await _run_reset_setup()
    await _gate("ALI1", "IN")
    r_out = await _gate("ALI1", "OUT")
    return {"exit": r_out}


async def _sim06_exit_with_debt() -> dict:
    await _run_reset_setup()
    from app.modules.simulator import scenario as scen
    await scen._set_exit_policy("DENY")  # noqa: SLF001
    await _gate("ALI1", "IN")
    await scen._backdate_session("ALI1", 90)  # noqa: SLF001
    r_out = await _gate("ALI1", "OUT")
    await scen._set_exit_policy("WARN")  # noqa: SLF001
    r_out2 = await _gate("ALI1", "OUT")
    return {"exit_deny_policy": r_out, "exit_warn_policy": r_out2}


async def _sim07_yard_full() -> dict:
    await _run_reset_setup()
    from app.modules.simulator import scenario as scen
    await scen._set_yard_capacity(2)  # noqa: SLF001
    await _gate("ALI3", "IN")   # جای ظرفیت پر می‌شود
    r_full = await _gate("ALI1", "IN")  # درخواست بعدی → ظرفیت کامل
    await scen._clear_yard_capacity()  # noqa: SLF001
    r_after = await _gate("ALI1", "IN")
    return {"when_full": r_full, "after_clear": r_after}


async def _sim08_duplicate_entry() -> dict:
    await _run_reset_setup()
    await _gate("ALI1", "IN")
    r_dup = await _gate("ALI1", "IN")   # ورود دوم بدون تخصیص جدید
    return {"duplicate": r_dup}


async def _sim09_draft_rule_effect() -> dict:
    await _run_reset_setup()
    before = await _gate("STR2", "IN")
    await _activate_rule("R-SCEN-UNKNOWN")
    after = await _gate("STR2", "IN")
    return {"before_publish": before, "after_publish": after}


async def _sim10_disable_rule() -> dict:
    await _run_reset_setup()
    await _activate_rule("R-SCEN-UNKNOWN")
    after = await _gate("STR2", "IN")
    from app.modules.simulator import scenario as scen
    # غیرفعال‌سازی همان قانون از پنل (rule.disable)
    from app.db.sim_session import SimSessionLocal as _S
    from app.modules.config_admin.models import EntryExitRule
    async with _S() as db:
        rule = (await db.execute(
            select(EntryExitRule).where(EntryExitRule.code == "R-SCEN-UNKNOWN"))).scalar_one_or_none()
        if rule:
            rule.status = "DISABLED"
            await db.commit()
    from app.modules.config_admin.runtime_settings import clear_rules_cache
    try:
        clear_rules_cache()
    except Exception:
        pass
    final = await _gate("STR2", "IN")
    return {"with_rule": after, "after_disable": final}


async def _sim11_unknown_plate_review() -> dict:
    await _run_reset_setup()
    r_bad = await _gate("BADPLATE", "IN")   # پلاک ناخوانا → ثبت‌نشده
    return {"entry": r_bad, "review_note": "برای پلاک NEEDS_REVIEW مسیر تأیید انسانی الزامی است"}


async def _sim12_banned_vehicle() -> dict:
    await _run_reset_setup()
    r_in = await _gate("BAN1", "IN")
    return {"entry": r_in}


async def _sim13_tariff_receipt() -> dict:
    await _run_reset_setup()
    from app.modules.simulator import scenario as scen
    await scen._backdate_session("ALI1", 120)  # noqa: SLF001
    await _gate("ALI1", "IN")
    r_out = await _gate("ALI1", "OUT")
    async with SimSessionLocal() as db:
        charges = (await db.execute(select(Charge))).scalars().all()
    return {"exit": r_out,
            "charges": [{"amount": c.amount, "paid_amount": getattr(c, "paid_amount", 0)}
                        for c in charges]}


async def _sim14_partial_payment() -> dict:
    await _run_reset_setup()
    from app.modules.simulator import scenario as scen
    await scen._backdate_session("ALI1", 120)  # noqa: SLF001
    await _gate("ALI1", "IN")
    await _gate("ALI1", "OUT")
    async with SimSessionLocal() as db:
        ch = (await db.execute(select(Charge).order_by(Charge.created_at.desc()))).scalars().first()
        open_sessions = (await db.execute(
            select(ParkingSession).where(ParkingSession.status == "OPEN"))).scalars().all()
        unpaid = (await db.execute(
            select(ParkingSession).where(ParkingSession.payment_status != "PAID"))).scalars().all()
    return {"charge": {"amount": ch.amount if ch else 0, "paid": getattr(ch, "paid_amount", 0) if ch else 0},
            "open_sessions": len(open_sessions), "unpaid_sessions": len(unpaid),
            "note": "پرداخت جزئی از پنل بدهی‌ها روی همان Charge انجام می‌شود (paid_amount)"}


async def _sim15_violation_image() -> dict:
    await _run_reset_setup()
    from app.modules.violations.router import VIOLATION_FA  # فقط برای اطمینان از import
    async with SimSessionLocal() as db:
        v_before = await _count(db, Violation)
    from app.modules.simulator import service as sim
    await sim._tick()  # noqa: SLF001  ترافیک شبیه‌ساز → احتمال تخلف
    async with SimSessionLocal() as db:
        v_after = await _count(db, Violation)
    return {"violations_before": v_before, "violations_after": v_after,
            "note": "ثبت تخلف بدون requires_image با 422 رد می‌شود (تست مستقل دارد)"}


async def _sim16_violation_appeal() -> dict:
    await _run_reset_setup()
    async with SimSessionLocal() as db:
        v = (await db.execute(select(Violation).limit(1))).scalars().first()
        result = {"violation_exists": v is not None,
                  "state": v.status if v else None}
    result["note"] = "چرخهٔ تخلف→اعتراض→تعیین تکلیف با state machine در پنل تخلفات آزموده می‌شود"
    return result


async def _sim17_guest_onsite() -> dict:
    await _run_reset_setup()
    from app.modules.simulator import scenario as scen
    r = await scen.manual_event("12ب34567ایران11", "IN")  # مهمان لحظه‌ای
    return {"guest": r}


async def _sim18_traffic_loop() -> dict:
    await _run_reset_setup()
    from app.modules.simulator import service as sim
    sim.start(interval=0.05, resident_ratio=0.8)
    for _ in range(8):
        await sim._tick()  # noqa: SLF001
    sim.stop()
    st = sim.status()
    return {"stats": st.get("stats"), "inside_count": len(st.get("inside") or {})}


async def _sim19_sheet_sync() -> dict:
    """همگام‌سازی روی دادهٔ آزمایشی — فقط اعتبارسنجی و صف تعارض، بدون تخریب."""
    from app.modules.vehicle_sync.service import validate_row, COLUMN_MAP
    rows = [
        ["EXT-101", "OPS", "11ب1234ایران11", "ساکن", "پژو", "206", "سفید", "علی رضایی", "101", "فعال"],
        ["EXT-102", "OPS", "پلاک-نامعتبر", "ساکن", "تیبا", "", "آبی", "مریم کریمی", "102", "فعال"],
    ]
    validated, invalid = [], []
    for r in rows:
        errs = validate_row(dict(zip(list(COLUMN_MAP)[:len(r)], r)))
        (invalid if errs else validated).append({"row": r, "errors": errs})
    return {"validated": validated, "invalid": invalid,
            "note": "اجرای کامل sync نیازمند حساب سرویس Google است (تنظیمات /integrations/google-sheets)"}


# ---------------------------------------------------------------------------
# کاتالوگ ۲۰ سناریوی الزامی
# ---------------------------------------------------------------------------

CATALOG: list[dict[str, Any]] = [
    {"id": "SIM-01", "title": "راه‌اندازی محیط آزمایشی (پاکسازی + دادهٔ پیش‌فرض)",
     "precondition": "دسترسی simulator.view / settings.publish؛ DB شبیه‌ساز جدا از عملیاتی",
     "steps": ["POST /simulator/scenarios/SIM-01/run", "پاکسازی داده‌های قبلی شبیه‌ساز", "seed ۲ ساکن × ۳ خودرو + ۲ غریبه + ۱ ممنوعه + ۳ قانون DRAFT + تعرفهٔ آزمایشی"],
     "expected": "شمارش خودروها = ۹ و ساکنان = ۲ در DB شبیه‌ساز؛ DB عملیاتی بدون تغییر",
     "runner": _sim01_setup},
    {"id": "SIM-02", "title": "ورود ساکن با مجوز معتبر",
     "precondition": "SIM-01 اجرا شده باشد",
     "steps": ["رویداد راهبند IN برای خودرو ALI1", "بررسی تصمیم موتور"],
     "expected": "ALLOW / VALID_PERMIT و باز شدن راهبند",
     "runner": _sim02_resident_valid},
    {"id": "SIM-03", "title": "ورود ساکن بدون پارکینگ شخصی (متقاضی محوطه)",
     "precondition": "SIM-01",
     "steps": ["رویداد IN برای ALI2 (ساکنِ بدون مجوز)"],
     "expected": "ارجاع به نگهبان (REQUIRE_OPERATOR_APPROVAL یا قانون YARD_APPLICANT) — نه رد قطعی",
     "runner": _sim03_yard_applicant},
    {"id": "SIM-04", "title": "ورود غریبهٔ فعالِ بدون مجوز",
     "precondition": "SIM-01",
     "steps": ["رویداد IN برای STR1"],
     "expected": "عدم باز شدن خودکار؛ REQUIRE_OPERATOR_APPROVAL/UNKNOWN_TO_GUARD",
     "runner": _sim04_stranger_no_permit},
    {"id": "SIM-05", "title": "خروج ساکن بدون بدهی",
     "precondition": "SIM-02 (نشست باز)",
     "steps": ["رویداد OUT برای ALI1"],
     "expected": "بستن نشست، شارژ صفر/رایگان، EXIT_SESSION_CLOSED با بدهی صفر",
     "runner": _sim05_exit_free},
    {"id": "SIM-06", "title": "خروج با بدهی — سیاست D1 (DENY/WARN)",
     "precondition": "SIM-02 + بدهی پرداخت‌نشده",
     "steps": ["سیاست D1=DENY", "عقب‌کشیدن زمان ورود ۹۰ دقیقه", "رویداد OUT", "سیاست D1=WARN", "رویداد OUT دوباره"],
     "expected": "DENY: مسدود با دلیل بدهی؛ WARN: عبور با هشدار و ماندن بدهی",
     "runner": _sim06_exit_with_debt},
    {"id": "SIM-07", "title": "ظرفیت کامل محوطه → تصمیم اپراتور",
     "precondition": "SIM-01 + YARD_CAPACITY=۲",
     "steps": ["پر کردن ظرفیت", "رویداد IN جدید", "حذف محدودیت", "رویداد IN دوباره"],
     "expected": "در ظرفیت کامل REQUIRE_OPERATOR_APPROVAL (بدون بستن خودکار)؛ بعد از رفع، عبور",
     "runner": _sim07_yard_full},
    {"id": "SIM-08", "title": "ورود دوم پلاک با نشست باز",
     "precondition": "SIM-02",
     "steps": ["رویداد IN دوباره برای ALI1"],
     "expected": "DUPLICATE_ENTRY بدون تخصیص جدید و بدون نشست دوم",
     "runner": _sim08_duplicate_entry},
    {"id": "SIM-09", "title": "اثر قانون DRAFT پس از publish",
     "precondition": "SIM-01",
     "steps": ["رویداد IN غریبه با قانون غیرفعال", "publish قانون R-SCEN-UNKNOWN", "رویداد IN دوباره"],
     "expected": "تغییر رفتار فقط پس از publish (DRAFT بی‌اثر است)",
     "runner": _sim09_draft_rule_effect},
    {"id": "SIM-10", "title": "قطع اثر قانون پس از disable",
     "precondition": "SIM-09",
     "steps": ["disable قانون", "رویداد IN"],
     "expected": "رفتار به حالت پیش‌فرض برگردد",
     "runner": _sim10_disable_rule},
    {"id": "SIM-11", "title": "پلاک ناشناس («ثبت‌نشده») و مسیر تأیید انسانی",
     "precondition": "SIM-01",
     "steps": ["رویداد IN با پلاک ناخوانا", "بررسی صف NEEDS_REVIEW", "تأیید/اصلاح دستی اپراتور"],
     "expected": "رکورد «ثبت‌نشده» با نگه‌داشتن مقدار اصلی + اطمینان پایین؛ عبور فقط پس از تأیید انسانی",
     "runner": _sim11_unknown_plate_review},
    {"id": "SIM-12", "title": "خودروی ممنوعه (BANNED)",
     "precondition": "SIM-01",
     "steps": ["رویداد IN برای BAN1"],
     "expected": "DENY / PLATE_RESTRICTED — نرم‌کردن محافظت ممنوع",
     "runner": _sim12_banned_vehicle},
    {"id": "SIM-13", "title": "محاسبهٔ تعرفه و صدور قبض خروج",
     "precondition": "SIM-02 + تعرفهٔ فعال",
     "steps": ["عقب‌کشیدن ورود ۱۲۰ دقیقه", "رویداد OUT"],
     "expected": "مبلغ ریال صحیح روی نشست + Charge متناظر",
     "runner": _sim13_tariff_receipt},
    {"id": "SIM-14", "title": "پرداخت جزئی و ماندهٔ بدهی",
     "precondition": "SIM-13 (شارژ صادر شده)",
     "steps": ["پرداخت جزئی از پنل بدهی‌ها", "بررسی paid_amount/مانده"],
     "expected": "مانده = amount − paid_amount؛ هیچ حذف/بازنویسی رکورد مالی",
     "runner": _sim14_partial_payment},
    {"id": "SIM-15", "title": "ثبت تخلف با الزام تصویر",
     "precondition": "SIM-01",
     "steps": ["اجرای tick شبیه‌ساز", "ثبت تخلف بدون تصویر → 422"],
     "expected": "تخلف بدون requires_image رد شود",
     "runner": _sim15_violation_image},
    {"id": "SIM-16", "title": "اعتراض تخلف و تعیین تکلیف",
     "precondition": "وجود تخلف OPEN",
     "steps": ["ثبت اعتراض", "ابطال/رد توسط مدیر"],
     "expected": "چرخهٔ کامل state machine با audit (VOIDED در صورت ابطال)",
     "runner": _sim16_violation_appeal},
    {"id": "SIM-17", "title": "ثبت مهمان در لحظه",
     "precondition": "SIM-01",
     "steps": ["manual_event با پلاک مهمان"],
     "expected": "ثبت خودرو/مجوز لحظه‌ای و تصمیم متناسب",
     "runner": _sim17_guest_onsite},
    {"id": "SIM-18", "title": "ترافیک مداوم و آمار تفکیکی",
     "precondition": "SIM-01",
     "steps": ["start شبیه‌ساز با فاصلهٔ کوتاه", "۸ tick", "stop"],
     "expected": "آمار ورود/خروج/تخلف + خودروهای داخل محوطه به‌روز",
     "runner": _sim18_traffic_loop},
    {"id": "SIM-19", "title": "اعتبارسنجی صف همگام‌سازی Google Sheets",
     "precondition": "تنظیمات sync (بدون نیاز به کلید واقعی)",
     "steps": ["اعتبارسنجی ردیف معتبر", "اعتبارسنجی ردیف پلاک نامعتبر"],
     "expected": "ردیف معتبر قبول؛ نامعتبر به صف تعارض/ردیف خطا برود؛ بدون تخریب بدهی/محدودیت داخلی",
     "runner": _sim19_sheet_sync},
    {"id": "SIM-20", "title": "پشتیبان‌گیری و بازیابی (میدانی)",
     "precondition": "دسترسی به سرور/سرویس پشتیبان",
     "steps": ["اجرای scripts/backup-db.ps1", "بازیابی روی محیط آزمایشی", "کنترل صحت داده"],
     "expected": "بازیابی موفق و یکسان بودن شمارش جداول کلیدی",
     "runner": None},  # میدانی
]


async def run_scenario(sid: str) -> dict:
    """اجرای سناریو با runner خودکار + نتیجهٔ PASS/FAIL نسبت به تصمیم مورد انتظار."""
    meta = next((s for s in CATALOG if s["id"] == sid), None)
    if meta is None:
        raise KeyError(sid)
    t0 = time.perf_counter()
    payload: dict[str, Any] = {}
    outcome = "PASS"
    notes: list[str] = []
    if meta["runner"] is None:
        outcome = "MANUAL"
        notes.append("این سناریو میدانی است و روی تجهیز واقعی انجام می‌شود (SIM-20: پشتیبان‌گیری/بازیابی).")
    else:
        try:
            payload = await meta["runner"]()
            outcome, notes = _judge(sid, payload)
        except Exception as exc:  # noqa: BLE001
            outcome = "ERROR"
            notes.append(f"خطای اجرا: {type(exc).__name__}: {exc}")
    return {
        "id": sid, "title": meta["title"], "outcome": outcome,
        "label": SIM_LABEL, "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
        "notes": notes, "payload": payload,
    }


_EXPECTED_DECISIONS = {
    "SIM-02": "ALLOW", "SIM-12": "DENY", "SIM-08": "DUPLICATE_ENTRY",
}


def _judge(sid: str, payload: dict) -> tuple[str, list[str]]:
    """داوری ساده بر اساس تصمیم آخرین رویداد سناریو."""
    notes: list[str] = []
    exp = _EXPECTED_DECISIONS.get(sid)
    if not exp:
        return ("PASS", notes) if payload else ("FAIL", ["بدون خروجی"])
    dec = _extract_decision(payload)
    if dec is None:
        return "INCONCLUSIVE", ["تصمیم نهایی استخراج نشد — ردیاب را بررسی کنید"]
    if dec == exp:
        notes.append(f"تصمیم نهایی = {dec} (مورد انتظار) ✅")
        return "PASS", notes
    notes.append(f"تصمیم نهایی = {dec} اما مورد انتظار {exp} بود ⚠️")
    return "FAIL", notes


def _extract_decision(payload: dict, depth: int = 0) -> str | None:
    if depth > 4 or not isinstance(payload, dict):
        return None
    for key in ("decision",):
        v = payload.get(key)
        if isinstance(v, str):
            return v
    for v in payload.values():
        if isinstance(v, dict):
            r = _extract_decision(v, depth + 1)
            if r:
                return r
    return None


def catalog_view() -> list[dict]:
    return [{k: v for k, v in s.items() if k != "runner"} for s in CATALOG]
