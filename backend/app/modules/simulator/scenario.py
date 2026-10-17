"""سناریوی آزمایشی شبیه‌ساز (موج ۱۰):
پاکسازی کامل داده‌ها (به‌جز ادمین/تنظیمات/زیرساخت) → ساخت سناریوی آموزشی:
  • ۲ ساکن (علی رضایی، مریم کریمی) — هر کدام یک واحد
  • هر ساکن ۳ خودرو: اولی=پارکینگ خودش، دومی=متقاضی محوطه، سومی=پارکینگ دفنی
  • ۲ خودرو غریبه (فعالِ بدون مجوز)
  • ۳ قانون DRAFT (ساکنِ خودش / متقاضی محوطه / ناشناس→نگهبان)
و اجرای گام‌به‌گام سناریو با توضیح فارسیِ هر تصمیم.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.session import AsyncSessionLocal
from app.modules.access_control.models import AccessEvent, ParkingSession
from app.modules.complexes.models import Complex, Tower, Unit
from app.modules.config_admin.models import EntryExitRule
from app.modules.devices.models import Gate
from app.modules.parking.models import ParkingAssignment, ParkingSpace
from app.modules.residents.models import Person, UnitOccupancy
from app.modules.vehicles.models import AccessPermit, Vehicle
from app.shared.plate import normalize_plate

# ---------------------------------------------------------------------------
# جدول‌هایی که پاک نمی‌شوند (زیرساخت + ادمین + تنظیمات)
# ---------------------------------------------------------------------------
KEEP_TABLES = {
    "alembic_version",
    # ادمین و دسترسی‌ها
    "users", "roles", "permissions", "user_roles", "role_permissions",
    "refresh_tokens",
    # تنظیمات و داده‌های پایه
    "app_settings", "app_settings_history", "plate_regions",
    "vehicle_groups", "violation_types", "tariffs",
}
# توجه: gates/devices پاک می‌شوند (به‌خاطر FK به complexes) و در seed دوباره ساخته می‌شوند.

REASON_FA = {
    "VALID_PERMIT": "مجوز معتبر",
    "EXIT_SESSION_CLOSED": "نشست پارکینگ بسته شد",
    "NO_ACTIVE_PERMIT": "بدون مجوز فعال",
    "PLATE_NOT_READABLE": "پلاک خوانده نشد",
    "VEHICLE_NOT_REGISTERED": "خودرو ثبت نشده",
    "VEHICLE_INACTIVE": "خودرو غیرفعال",
    "PLATE_RESTRICTED": "پلاک محدود/ممنوع",
    "PERMIT_INVALID_NOW": "مجوز در این زمان نامعتبر است",
    "SESSION_ALREADY_OPEN": "نشست بازِ پیشین وجود دارد",
    "DUPLICATE_ENTRY_SESSION_OPEN": "ورود تکراری — نشست باز",
    "EXIT_UNPAID_BLOCKED": "خروج با بدهی پرداخت‌نشده مسدود شد",
    "RULE_REFER_GUARD": "طبق قانون → ارجاع به نگهبان",
    "YARD_APPLICANT": "متقاضی محوطه → ارجاع به نگهبان",
    "UNKNOWN_TO_GUARD": "ناشناس → ارجاع به نگهبان",
    "YARD_CAPACITY_FULL": "ظرفیت محوطه پر است",
    "NO_OPEN_SESSION_FOR_EXIT": "بدون نشست باز برای خروج",
}
DECISION_FA = {
    "ALLOW": "اجازه عبور",
    "ALLOW_WITH_WARNING": "عبور با هشدار",
    "DENY": "عدم اجازه",
    "UNKNOWN_PLATE": "پلاک ناشناس",
    "REQUIRE_OPERATOR_APPROVAL": "نیازمند تأیید نگهبان",
}

# ---------------------------------------------------------------------------
# تعریف موجودیت‌های سناریو
# ---------------------------------------------------------------------------
RESIDENTS = [
    {
        "first_name": "علی", "last_name": "رضایی", "mobile": "09121000001",
        "unit_number": "101", "floor": 1,
        "vehicles": [
            {"role": "ALI1", "label": "خودرو اول — پارکینگ خودش",
             "plate_raw": "12 ب 345 ایران 11", "color": "نقره‌ای", "brand": "پژو پارس"},
            {"role": "ALI2", "label": "خودرو دوم — متقاضی محوطه",
             "plate_raw": "23 ج 456 ایران 11", "color": "سفید", "brand": "سمند"},
            {"role": "ALI3", "label": "خودرو سوم — پارکینگ دفنی",
             "plate_raw": "34 د 567 ایران 11", "color": "مشکی", "brand": "کیا سراتو"},
        ],
    },
    {
        "first_name": "مریم", "last_name": "کریمی", "mobile": "09121000002",
        "unit_number": "102", "floor": 1,
        "vehicles": [
            {"role": "MRY1", "label": "خودرو اول — پارکینگ خودش",
             "plate_raw": "45 س 678 ایران 11", "color": "آبی", "brand": "تیبا"},
            {"role": "MRY2", "label": "خودرو دوم — متقاضی محوطه",
             "plate_raw": "56 ص 789 ایران 11", "color": "خاکستری", "brand": "کوییک"},
            {"role": "MRY3", "label": "خودرو سوم — پارکینگ دفنی",
             "plate_raw": "67 ط 890 ایران 11", "color": "قرمز", "brand": "شانگن"},
        ],
    },
]

STRANGERS = [
    {"role": "STR1", "label": "غریبه ۱ — فعال بدون مجوز",
     "plate_raw": "78 م 901 ایران 22", "color": "سفید", "brand": "پراید"},
    {"role": "STR2", "label": "غریبه ۲ — فعال بدون مجوز",
     "plate_raw": "89 ن 012 ایران 36", "color": "سبز", "brand": "وانت نیسان"},
]

SPACE_MAP = {  # role خودرو → فضای اختصاص‌یافته
    "ALI1": {"code": "P-A-101", "type": "PRIVATE", "zone": "A", "floor": -1, "label": "پارکینگ شخصی علی"},
    "ALI3": {"code": "D-A-01",  "type": "BURIED",  "zone": "D", "floor": -2, "label": "پارکینگ دفنی علی"},
    "MRY1": {"code": "P-B-102", "type": "PRIVATE", "zone": "B", "floor": -1, "label": "پارکینگ شخصی مریم"},
    "MRY3": {"code": "D-B-02",  "type": "BURIED",  "zone": "D", "floor": -2, "label": "پارکینگ دفنی مریم"},
}
PERMIT_ROLES = {"ALI1", "ALI3", "MRY1", "MRY3"}  # خودروهای دارای مجوز دائم

DRAFT_RULES = [
    {
        "code": "R-SCEN-RESIDENT", "name": "ساکنِ خودش", "dir": "ANY",
        "description": "ساکن با مجوز معتبر: پیام خوش‌آمد + صدور رسید (آزمایشی)",
        "priority": 10, "mode": "ALL",
        "conditions": [{"field": "is_resident", "op": "true"},
                        {"field": "has_valid_permit", "op": "true"}],
        "actions": [{"action": "show_message", "params": {"text": "خوش آمدید — ساکنِ مجموعه"}},
                    {"action": "issue_receipt", "params": {}}],
    },
    {
        "code": "R-SCEN-YARD", "name": "متقاضی محوطه", "dir": "IN",
        "description": "ساکنِ بدون مجوز (خودرو دوم): ارجاع به نگهبان برای بررسی متقاضی محوطه",
        "priority": 20, "mode": "ALL",
        "conditions": [{"field": "is_resident", "op": "true"},
                        {"field": "has_valid_permit", "op": "false"}],
        "actions": [{"action": "refer_to_guard", "params": {"reason": "YARD_APPLICANT"}}],
    },
    {
        "code": "R-SCEN-UNKNOWN", "name": "ناشناس → نگهبان", "dir": "IN",
        "description": "هر خودروی غیرساکنِ بدون مجوز (غریبه): ارجاع به نگهبان",
        "priority": 30, "mode": "ALL",
        "conditions": [{"field": "is_resident", "op": "false"},
                        {"field": "has_valid_permit", "op": "false"}],
        "actions": [{"action": "refer_to_guard", "params": {"reason": "UNKNOWN_TO_GUARD"}}],
    },
]

# ---------------------------------------------------------------------------
# گام‌های سناریو — هر گام یا «رویداد راهبند» است یا «فعال‌سازی قانون» یا «خلاصه»
# ---------------------------------------------------------------------------
STEPS = [
    {"action": "gate", "role": "ALI1", "direction": "IN",
     "title": "ورود خودرو اول علی (پارکینگ خودش)"},
    {"action": "gate", "role": "ALI1", "direction": "OUT",
     "title": "خروج خودرو اول علی"},
    {"action": "gate", "role": "ALI2", "direction": "IN",
     "title": "ورود خودرو دوم علی (متقاضی محوطه — بدون مجوز)"},
    {"action": "gate", "role": "MRY1", "direction": "IN",
     "title": "ورود خودرو اول مریم (پارکینگ خودش)"},
    {"action": "gate", "role": "MRY3", "direction": "IN",
     "title": "ورود خودرو سوم مریم (پارکینگ دفنی)"},
    {"action": "gate", "role": "STR1", "direction": "IN",
     "title": "ورود غریبه ۱ (فعال بدون مجوز)"},
    {"action": "gate", "role": "BADPLATE", "direction": "IN",
     "title": "ورود با پلاکِ ناخوانا (تست خطای خوانش)"},
    {"action": "activate_rule", "rule": "R-SCEN-UNKNOWN",
     "title": "فعال‌سازی قانون «ناشناس → نگهبان»"},
    {"action": "gate", "role": "STR2", "direction": "IN",
     "title": "ورود مجدد غریبه — این‌بار با قانون فعال"},
    {"action": "activate_rule", "rule": "R-SCEN-YARD",
     "title": "فعال‌سازی قانون «متقاضی محوطه»"},
    {"action": "gate", "role": "ALI2", "direction": "IN",
     "title": "ورود دوباره خودرو دوم علی — با قانون فعال"},
    {"action": "activate_rule", "rule": "R-SCEN-RESIDENT",
     "title": "فعال‌سازی قانون «ساکنِ خودش»"},
    {"action": "gate", "role": "MRY1", "direction": "OUT",
     "title": "خروج خودرو اول مریم — با قانون ساکن فعال"},
    {"action": "summary", "title": "خلاصه وضعیت نهایی"},
]


# ---------------------------------------------------------------------------
# پاکسازی کامل (به‌جز جدول‌های KEEP_TABLES)
# ---------------------------------------------------------------------------
async def cleanup_db(db: AsyncSession) -> int:
    tables = reversed(Base.metadata.sorted_tables)
    deleted = 0
    await db.execute(text("PRAGMA foreign_keys=OFF")) if db.bind.dialect.name == "sqlite" else None
    for t in tables:
        if t.name in KEEP_TABLES:
            continue
        try:
            res = await db.execute(text(f'DELETE FROM "{t.name}"'))
            deleted += int(res.rowcount or 0)
        except Exception:
            pass
    if db.bind.dialect.name == "sqlite":
        await db.execute(text("PRAGMA foreign_keys=ON"))
    await db.commit()
    return deleted


# ---------------------------------------------------------------------------
# ساخت سناریو
# ---------------------------------------------------------------------------
async def seed_scenario(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)

    # مجتمع/برج/واحدها
    cx = Complex(code="SCEN", name="مجتمع آموزشی شبیه‌ساز", address="تهران", is_active=True)
    db.add(cx)
    await db.flush()
    tw = Tower(complex_id=cx.id, code="T1", name="برج A", floor_count=5, is_active=True)
    db.add(tw)
    await db.flush()
    units = {}
    for r in RESIDENTS:
        u = Unit(tower_id=tw.id, unit_number=r["unit_number"],
                 floor_number=r["floor"], status="ACTIVE", is_active=True)
        db.add(u)
        units[r["unit_number"]] = u
    await db.flush()

    # دروازه‌ها (بعد از پاکسازی همیشه ساخته می‌شوند)
    for code, name, direction in [("GATE-IN-01", "ورودی اصلی", "IN"),
                                   ("GATE-OUT-01", "خروجی اصلی", "OUT")]:
        g = (await db.execute(select(Gate).where(Gate.code == code))).scalar_one_or_none()
        if g is None:
            db.add(Gate(complex_id=cx.id, code=code, name=name,
                        gate_type="VEHICLE", direction=direction, status="ONLINE"))
    await db.flush()

    # فضاهای پارکینگ + ساکن‌ها + خودروها
    spaces = {}
    for role, sp in SPACE_MAP.items():
        s = ParkingSpace(complex_id=cx.id, code=sp["code"], number=sp["code"],
                         floor=sp["floor"], zone=sp["zone"],
                         parking_type=sp["type"], status="FREE", is_active=True)
        db.add(s)
        spaces[role] = s
    await db.flush()

    vehicle_ids = {}
    plate_by_role = {}
    for r in RESIDENTS:
        p = Person(first_name=r["first_name"], last_name=r["last_name"],
                   mobile=r["mobile"], person_type="OWNER", is_active=True)
        db.add(p)
        await db.flush()
        u = units[r["unit_number"]]
        db.add(UnitOccupancy(unit_id=u.id, person_id=p.id,
                             occupancy_type="OWNER", is_primary=True, status="ACTIVE"))
        for v in r["vehicles"]:
            norm = normalize_plate(v["plate_raw"]) or v["plate_raw"]
            veh = Vehicle(
                owner_person_id=p.id, unit_id=u.id,
                plate_raw=v["plate_raw"], plate_normalized=norm,
                plate_letter=None, plate_province_code="11",
                plate_province="تهران", plate_city="تهران",
                plate_type="PERSONAL", vehicle_type="CAR",
                brand=v["brand"], color=v["color"], is_active=True,
                notes=f"SCEN:{v['role']}|{v['label']}",
            )
            db.add(veh)
            await db.flush()
            vehicle_ids[v["role"]] = veh.id
            plate_by_role[v["role"]] = v["plate_raw"]
            if v["role"] in PERMIT_ROLES:
                db.add(AccessPermit(
                    vehicle_id=veh.id, plate_normalized=veh.plate_normalized,
                    permit_type="PERMANENT", valid_from=now,
                    valid_until=now + timedelta(days=3650),
                    status="ACTIVE", reason="مجوز دائم ساکن — سناریوی آزمایشی"))
            if v["role"] in SPACE_MAP:
                db.add(ParkingAssignment(
                    parking_space_id=spaces[v["role"]].id, unit_id=u.id,
                    vehicle_id=veh.id, assignment_type="PERMANENT",
                    starts_at=now, status="ACTIVE"))

    # غریبه‌ها — فعالِ بدون مجوز، بدون واحد
    for v in STRANGERS:
        norm = normalize_plate(v["plate_raw"]) or v["plate_raw"]
        veh = Vehicle(
            plate_raw=v["plate_raw"], plate_normalized=norm,
            plate_letter=None, plate_province_code=None,
            plate_province=None, plate_city=None,
            plate_type="PERSONAL", vehicle_type="CAR",
            brand=v["brand"], color=v["color"], is_active=True,
            notes=f"SCEN:{v['role']}|{v['label']}",
        )
        db.add(veh)
        await db.flush()
        vehicle_ids[v["role"]] = veh.id
        plate_by_role[v["role"]] = v["plate_raw"]

    # سه قانون DRAFT — کد سناریو در description نشانه‌گذاری می‌شود تا بعداً قابل پیدا کردن باشد
    for rl in DRAFT_RULES:
        db.add(EntryExitRule(
            name=rl["name"], description=f"SCEN-RULE:{rl['code']}|{rl['description']}",
            direction=rl["dir"], priority=rl["priority"], enabled=True,
            condition_mode=rl["mode"], conditions=rl["conditions"],
            actions=rl["actions"], status="DRAFT"))

    await db.commit()
    return {
        "complex": cx.name, "tower": tw.name,
        "units": [r["unit_number"] for r in RESIDENTS],
        "residents": [f'{r["first_name"]} {r["last_name"]}' for r in RESIDENTS],
        "vehicles": len(RESIDENTS) * 3 + len(STRANGERS),
        "permits": len(PERMIT_ROLES),
        "spaces": list(SPACE_MAP.keys()),
        "draft_rules": [rl["name"] for rl in DRAFT_RULES],
        "strangers": len(STRANGERS),
    }


async def setup_scenario() -> dict:
    """پاکسازی کامل + ساخت سناریو (به‌جز ادمین/تنظیمات/زیرساخت)."""
    # توقف حلقه شبیه‌ساز و پاک‌سازی وضعیت درون‌مانی
    from app.modules.simulator import service as sim
    sim.stop()
    sim._state["inside"] = {}
    sim._state["stats"] = {"events": 0, "entry": 0, "exit": 0, "violations": 0,
                            "resident_entries": 0, "guest_entries": 0}
    sim._state["last"] = None
    async with AsyncSessionLocal() as db:
        deleted = await cleanup_db(db)
        summary = await seed_scenario(db)
    _state["step_index"] = 0
    _state["steps_log"] = []
    return {"cleanup_deleted_rows": deleted, "scenario": summary}


# ---------------------------------------------------------------------------
# ابزارهای گام‌به‌گام
# ---------------------------------------------------------------------------
_state = {"step_index": 0, "steps_log": []}


async def _role_plate(role: str) -> str | None:
    if role == "BADPLATE":
        return "پلاک نامفهوم"  # عمداً غیرقابل نرمال‌سازی
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Vehicle).where(Vehicle.notes.like(f"SCEN:{role}|%")))).scalars().all()
        return rows[0].plate_raw if rows else None


def _explain(action: str, result: dict, role: str | None, direction: str | None) -> list[str]:
    """توضیح فارسی گام‌به‌گام از نتیجه تصمیم."""
    out: list[str] = []
    if action != "gate" or result is None:
        return out
    dec = result.get("decision")
    reason = result.get("decision_reason")
    out.append(f"تصمیم سامانه: {DECISION_FA.get(dec, dec)} ({reason and REASON_FA.get(reason, reason) or '—'})")
    barrier = result.get("barrier_action")
    out.append("راهبند: باز شد ✅" if barrier == "OPEN" else "راهبند: بسته ماند ⛔")
    if dec == "ALLOW" and reason == "VALID_PERMIT":
        out.append("چرا؟ خودرو فعال است، مجوز دائم ساکن دارد و هنوز نشست بازی ندارد.")
    elif reason == "NO_ACTIVE_PERMIT":
        out.append("چرا؟ خودرو در سامانه ثبت و فعال است اما هیچ مجوز فعالی ندارد → پلاک ناشناس تلقی می‌شود.")
    elif reason == "PLATE_NOT_READABLE":
        out.append("چرا؟ متن خوانده‌شده قالب پلاک ایرانی (۲ رقم + حرف + ۳ رقم + ایران + استان) را ندارد.")
    elif reason == "RULE_REFER_GUARD" or reason in ("YARD_APPLICANT", "UNKNOWN_TO_GUARD"):
        out.append("چرا؟ قانون ACTIVE تازه فعال شد و مسیر پیش‌فرض را به «ارجاع به نگهبان» تغییر داد — "
                    "این تفاوت با گام قبلیِ همین خودرو را مقایسه کن.")
    elif reason == "EXIT_SESSION_CLOSED":
        sess = result.get("session") or {}
        dur = sess.get("duration_seconds")
        amount = sess.get("final_amount", 0)
        extra = f" مدت {dur} ثانیه، مبلغ {amount:,} تومان." if dur is not None else ""
        out.append(f"نشست پارکینگ بسته و فضا آزاد شد.{extra}")
    elif reason == "SESSION_ALREADY_OPEN":
        out.append("چرا؟ برای همین پلاک قبلاً نشست بازی وجود دارد → ورود تکراری با هشدار.")
    if result.get("parking"):
        out.append(f'فضای تخصیص‌یافته: {result["parking"].get("code")} (زون {result["parking"].get("zone")})')
    if result.get("unit"):
        out.append(f'واحد: {result["unit"].get("unit_number")} — {result["unit"].get("tower")}')
    trace = result.get("rule_trace")
    if trace:
        out.append(f'قانون اعمال‌شده: «{trace.get("rule_name")}»')
    warns = [w for w in (result.get("warnings") or []) if w != "RULES_ENGINE_ERROR"]
    if warns:
        out.append("هشدارها: " + "، ".join(warns))
    return out


async def _run_gate_step(role: str, direction: str) -> dict:
    from app.modules.access_control.service import GateDecisionService
    plate_raw = await _role_plate(role)
    gate_code = "GATE-IN-01" if direction == "IN" else "GATE-OUT-01"
    async with AsyncSessionLocal() as db:
        result = await GateDecisionService.process_plate_event(
            db, gate_code=gate_code, direction=direction, plate_raw=plate_raw,
            source_event_id=f"scen-{role}-{direction}-{datetime.now(timezone.utc).timestamp()}",
            confidence=98.0, raw_payload={"source": "scenario"})
    role_label = next((v["label"] for r in RESIDENTS for v in r["vehicles"] if v["role"] == role), None)
    if role_label is None:
        role_label = next((v["label"] for v in STRANGERS if v["role"] == role), "پلاک ناخوانا")
    return {
        "action": "gate", "role": role, "role_label": role_label,
        "direction": direction, "gate_code": gate_code, "plate_raw": plate_raw,
        "result": result, "explanation": _explain("gate", result, role, direction),
    }


async def _activate_rule(code: str) -> dict:
    async with AsyncSessionLocal() as db:
        rl = (await db.execute(select(EntryExitRule).where(
            EntryExitRule.description.like(f"SCEN-RULE:{code}|%")))).scalar_one_or_none()
        if rl is None:
            return {"action": "activate_rule", "rule": code, "error": "RULE_NOT_FOUND"}
        rl.status = "ACTIVE"
        rl.enabled = True
        rl.approved_by = "scenario"
        rl.approved_at = datetime.now(timezone.utc)
        await db.commit()
        return {
            "action": "activate_rule", "rule": code, "rule_id": rl.id,
            "rule_name": rl.name,
            "explanation": [
                f"قانون «{rl.name}» از DRAFT به ACTIVE تغییر کرد.",
                "از این لحظه این قانون برای همه رویدادهای مطابق شرطش اعمال می‌شود.",
                "برای بازگشت، در صفحه «قوانین ورود/خروج» وضعیت را به DRAFT برگردان.",
            ],
        }


async def next_step() -> dict:
    i = _state["step_index"]
    if i >= len(STEPS):
        return {"finished": True, "total": len(STEPS),
                "message": "همه گام‌ها اجرا شد — برای شروع مجدد «بازنشانی گام‌ها» را بزن."}
    step = STEPS[i]
    if step["action"] == "gate":
        out = await _run_gate_step(step["role"], step["direction"])
    elif step["action"] == "activate_rule":
        out = await _activate_rule(step["rule"])
    else:
        snap = await scenario_state()
        out = {
            "action": "summary",
            "explanation": [
                f'خودروهای داخل مجموعه: {snap["inside_count"]}',
                f'فضاهای اشغال‌شده: {snap["occupied_spaces"]} از {snap["total_spaces"]}',
                f'قوانین فعال: {snap["active_rules"]} | DRAFT: {snap["draft_rules"]}',
                "همه رویدادها در «گزارش‌ها ← رویدادهای تردد» و «جریمه/تخلف» قابل بررسی هستند.",
            ],
        }
    _state["step_index"] = i + 1
    entry = {"index": i + 1, "total": len(STEPS), "title": step["title"], **out}
    _state["steps_log"].append(entry)
    return entry


def reset_steps() -> dict:
    _state["step_index"] = 0
    _state["steps_log"] = []
    return {"step_index": 0, "total": len(STEPS)}


# ---------------------------------------------------------------------------
# وضعیت سناریو + رویداد دستی
# ---------------------------------------------------------------------------
async def scenario_state() -> dict:
    async with AsyncSessionLocal() as db:
        residents_out = []
        for r in RESIDENTS:
            vs = []
            for v in r["vehicles"]:
                veh = (await db.execute(
                    select(Vehicle).where(Vehicle.notes.like(f"SCEN:{v['role']}|%")))).scalars().first()
                if veh is None:
                    continue
                permit = (await db.execute(
                    select(AccessPermit).where(
                        AccessPermit.plate_normalized == veh.plate_normalized,
                        AccessPermit.status == "ACTIVE"))).scalars().first()
                space = (await db.execute(
                    select(ParkingSpace).join(ParkingAssignment, ParkingAssignment.parking_space_id == ParkingSpace.id)
                    .where(ParkingAssignment.vehicle_id == veh.id,
                           ParkingAssignment.status == "ACTIVE"))).scalars().first()
                vs.append({"role": v["role"], "label": v["label"],
                           "plate_raw": veh.plate_raw, "plate_normalized": veh.plate_normalized,
                           "is_active": veh.is_active,
                           "has_permit": permit is not None,
                           "space_code": space.code if space else None,
                           "space_type": space.parking_type if space else None})
            residents_out.append({"name": f'{r["first_name"]} {r["last_name"]}',
                                   "unit": r["unit_number"], "vehicles": vs})
        strangers_out = []
        for v in STRANGERS:
            veh = (await db.execute(
                select(Vehicle).where(Vehicle.notes.like(f"SCEN:{v['role']}|%")))).scalars().first()
            if veh:
                strangers_out.append({"role": v["role"], "label": v["label"],
                                       "plate_raw": veh.plate_raw, "is_active": veh.is_active})
        rules = (await db.execute(select(EntryExitRule).where(
            EntryExitRule.description.like("SCEN-RULE:%")).order_by(EntryExitRule.priority))).scalars().all()
        spaces = (await db.execute(select(ParkingSpace).where(
            ParkingSpace.code.in_([s["code"] for s in SPACE_MAP.values()])))).scalars().all()
        from sqlalchemy import func
        open_sessions = await db.scalar(select(func.count()).select_from(ParkingSession)
                                         .where(ParkingSession.status == "OPEN"))
        events_total = await db.scalar(select(func.count()).select_from(AccessEvent))
        return {
            "residents": residents_out,
            "strangers": strangers_out,
            "rules": [{"code": ((r.description or "").split("|")[0].replace("SCEN-RULE:", "")),
                        "name": r.name, "status": r.status, "enabled": r.enabled,
                        "priority": r.priority} for r in rules],
            "spaces": [{"code": s.code, "type": s.parking_type, "status": s.status} for s in spaces],
            "inside_count": int(open_sessions or 0),
            "occupied_spaces": len([s for s in spaces if s.status == "OCCUPIED"]),
            "total_spaces": len(spaces),
            "active_rules": len([r for r in rules if r.status == "ACTIVE"]),
            "draft_rules": len([r for r in rules if r.status != "ACTIVE"]),
            "events_total": int(events_total or 0),
            "step_index": _state["step_index"],
            "total_steps": len(STEPS),
        }


async def manual_event(plate_raw: str, direction: str = "IN", gate_code: str | None = None) -> dict:
    """رویداد دستی: کاربر پلاک را (کشویی یا تایپی) می‌دهد و نتیجه با توضیح برمی‌گردد."""
    from app.modules.access_control.service import GateDecisionService
    if not plate_raw or not plate_raw.strip():
        return {"error": "PLATE_REQUIRED"}
    direction = "OUT" if str(direction).upper() == "OUT" else "IN"
    gate_code = gate_code or ("GATE-IN-01" if direction == "IN" else "GATE-OUT-01")
    role = None
    async with AsyncSessionLocal() as db:
        # تشخیص نقش (اگر پلاک متعلق به سناریو باشد)
        rows = (await db.execute(select(Vehicle).where(
            Vehicle.notes.like("SCEN:%")))).scalars().all()
        from app.shared.plate import normalize_plate
        norm = normalize_plate(plate_raw)
        for r in rows:
            if r.plate_normalized == norm:
                role = (r.notes or "").split("|")[0].replace("SCEN:", "")
                break
        result = await GateDecisionService.process_plate_event(
            db, gate_code=gate_code, direction=direction, plate_raw=plate_raw.strip(),
            source_event_id=f"scen-manual-{datetime.now(timezone.utc).timestamp()}",
            confidence=None, raw_payload={"source": "scenario-manual"})
    return {
        "action": "manual", "role": role, "direction": direction,
        "gate_code": gate_code, "plate_raw": plate_raw.strip(),
        "result": result, "explanation": _explain("gate", result, role, direction),
    }


def steps_log() -> list:
    return _state["steps_log"]
