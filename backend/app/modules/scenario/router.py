"""موج ۶ — سناریوساز: پاکسازی انتخابی، بارگذاری ساختار، اجرای سناریو."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, delete as sqldel, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.audit import write_audit
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_any_permission
from app.db.session import get_db
from app.modules.access_control.models import AccessEvent, ParkingSession, PlateRecognitionEvent
from app.modules.complexes.models import Complex, Tower, Unit
from app.modules.finance.models import Charge, Payment, PaymentAllocation
from app.modules.identity.models import RefreshToken, User, user_roles
from app.modules.parking.models import ParkingAssignment, ParkingOccupancy, ParkingSpace
from app.modules.residents.models import Person, UnitOccupancy
from app.modules.vehicles.models import AccessPermit, Vehicle, VehicleRestriction
from app.modules.violations.models import Violation, ViolationAppeal
from app.modules.identity.models import Role, Permission, role_permissions
from app.modules.config_admin.models import EntryExitRule
from app.modules.identity.models import User as _U

router = APIRouter(prefix="/scenario", tags=["Scenario"])

# ترتیب حذف بر اساس وابستگی FK (اول فرزند، آخر پدر)
ASSOCIATION_TABLES = {
    # users: user_roles در حلقهٔ مدل _U به‌تفکیک برای هر کاربر غیرادمین حذف می‌شود
    # تا لینک ادمین به نقش ADMIN حفظ شود (باگ قبلی: حذف گروهی → ادمین بی‌نقش → 403)
}

PURGE_MAP = {
    "events_sessions": [ParkingOccupancy, ParkingSession, AccessEvent, PlateRecognitionEvent],
    "finance":         [PaymentAllocation, Payment, Charge],
    "violations":      [ViolationAppeal, Violation],
    "vehicles":        [AccessPermit, VehicleRestriction, Vehicle],
    "persons":         [UnitOccupancy, Person],
    "units":           [Unit],
    "towers":          [Tower],
    "complexes":       [Complex],
    "parking_spaces":  [ParkingAssignment, ParkingSpace],
    "users":           [_U],
    "rules":           [EntryExitRule],
}


class PurgeBody(BaseModel):
    categories: list[str] = Field(default_factory=list)  # خالی = همه


@router.post("/purge")
async def purge(body: PurgeBody, db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("settings.publish"))):
    """موج ۶: پاکسازی انتخابی دسته‌ها. ادمین را حذف نمی‌کند."""
    cats = body.categories or list(PURGE_MAP.keys())
    unknown = [c for c in cats if c not in PURGE_MAP]
    if unknown:
        raise ConflictError(f"دستهٔ نامشخص: {unknown}")
    counts = {}
    for cat in cats:
        n = 0
        for tbl in ASSOCIATION_TABLES.get(cat, []):
            res = await db.execute(sqldel(tbl))
            n += res.rowcount or 0
        for model in PURGE_MAP[cat]:
            if model is _U:
                users = (await db.execute(select(_U).where(_U.username != "admin"))).scalars().all()
                for u in users:
                    await db.execute(sqldel(user_roles).where(user_roles.c.user_id == u.id))
                    await db.execute(sqldel(RefreshToken).where(RefreshToken.user_id == u.id))  # fix-dependents
                    from app.core.system_models import Notification
                    await db.execute(sqldel(Notification).where(Notification.recipient_user_id == u.id))
                    await db.delete(u)
                    n += 1
                continue
            rows = (await db.execute(select(model))).scalars().all()
            for r in rows:
                await db.delete(r); n += 1
        counts[cat] = n
    if user:
        await write_audit(db, user_id=user.id, action="SCENARIO_PURGE", module="scenario",
                          entity_type="scenario", entity_id="purge", new_values=counts)
    await db.commit()
    return {"success": True, "deleted": counts}


class UnitBody(BaseModel):
    tower_code: str = "T1"
    tower_name: str = "برج ۱"
    tower_floors: int = 10
    unit_number: str
    floor_number: int = 1


@router.post("/add-unit")
async def add_unit(body: UnitBody, db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("structure.edit", "settings.edit"))):
    cx = (await db.execute(select(Complex))).scalars().first()
    if cx is None:
        cx = Complex(code="ORKID", name="مجتمع ارکیده"); db.add(cx); await db.flush()
    tw = (await db.execute(select(Tower).where(Tower.code == body.tower_code))).scalars().first()
    if tw is None:
        tw = Tower(complex_id=cx.id, code=body.tower_code, name=body.tower_name,
                   floor_count=body.tower_floors, is_active=True)
        db.add(tw); await db.flush()
    dup = (await db.execute(select(Unit).where(Unit.tower_id == tw.id,
                                               Unit.unit_number == body.unit_number))).scalars().first()
    if dup:
        raise ConflictError(f"واحد {body.unit_number} قبلاً ثبت شده است")
    u = Unit(tower_id=tw.id, unit_number=body.unit_number, floor_number=body.floor_number, is_active=True)
    db.add(u)
    if user:
        await write_audit(db, user_id=user.id, action="SCENARIO_UNIT_ADD", module="scenario",
                          entity_type="unit", entity_id=u.id, new_values={"unit": body.unit_number})
    await db.commit()
    await db.refresh(u)
    return {"id": u.id, "unit_number": u.unit_number, "tower": tw.name}


class ResidentBody(BaseModel):
    unit_id: str
    first_name: str
    last_name: str
    mobile: str | None = None
    national_code: str | None = None
    person_type: str = "OWNER"   # OWNER / TENANT
    is_primary: bool = True


@router.post("/add-resident")
async def add_resident(body: ResidentBody, db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("structure.edit", "settings.edit"))):
    unit = await db.get(Unit, body.unit_id)
    if not unit:
        raise NotFoundError("واحد یافت نشد")
    p = Person(first_name=body.first_name, last_name=body.last_name,
               mobile=body.mobile, national_code=body.national_code,
               person_type=body.person_type)
    db.add(p); await db.flush()
    occ = UnitOccupancy(unit_id=unit.id, person_id=p.id,
                        occupancy_type=body.person_type, is_primary=body.is_primary,
                        start_date=__import__("datetime").date.today())
    db.add(occ)
    if user:
        await write_audit(db, user_id=user.id, action="SCENARIO_RESIDENT_ADD", module="scenario",
                          entity_type="person", entity_id=p.id,
                          new_values={"unit": unit.unit_number, "name": f"{body.first_name} {body.last_name}"})
    await db.commit()
    return {"person_id": p.id, "name": f"{p.first_name} {p.last_name}"}


class VehicleBody(BaseModel):
    person_id: str | None = None
    unit_id: str | None = None
    plate_raw: str
    plate_letter: str | None = None
    plate_province_code: str | None = None
    brand: str | None = None
    model: str | None = None
    color: str | None = None
    vehicle_type: str = "CAR"
    plate_type: str = "PERSONAL"
    grant_permit: bool = True
    permit_days: int = 365


@router.post("/add-vehicle")
async def add_vehicle(body: VehicleBody, db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("vehicles.create", "settings.edit"))):
    from app.shared.plate import normalize_plate
    norm = normalize_plate(body.plate_raw) or body.plate_raw
    dup = (await db.execute(select(Vehicle).where(Vehicle.plate_normalized == norm))).scalars().first()
    if dup:
        raise ConflictError(f"خودرو با پلاک {norm} قبلاً ثبت شده است")
    v = Vehicle(owner_person_id=body.person_id, unit_id=body.unit_id,
                plate_raw=body.plate_raw, plate_normalized=norm,
                plate_letter=body.plate_letter, plate_province_code=body.plate_province_code,
                brand=body.brand, model=body.model, color=body.color,
                vehicle_type=body.vehicle_type, plate_type=body.plate_type, is_active=True)
    db.add(v); await db.flush()
    if body.grant_permit:
        from datetime import datetime, timedelta, timezone as tz
        db.add(AccessPermit(vehicle_id=v.id, plate_normalized=norm, status="ACTIVE",
                            permit_type="PERMANENT",
                            valid_from=datetime.now(tz.utc) - timedelta(hours=1),
                            valid_until=datetime.now(tz.utc) + timedelta(days=body.permit_days),
                            max_entries=None, used_entries=0))
    if user:
        await write_audit(db, user_id=user.id, action="SCENARIO_VEHICLE_ADD", module="scenario",
                          entity_type="vehicle", entity_id=v.id, new_values={"plate": norm})
    await db.commit()
    return {"vehicle_id": v.id, "plate_normalized": norm}


@router.post("/setup-default")
async def setup_default(db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("settings.publish"))):
    """سناریوی پیش‌فرض کارفرما:
    ۲ ساکن × ۳ ماشین (اولی=پارکینگ خودش، دومی=محوطه، سومی=دفنی) + ۲ خودروی غریبه."""
    from app.shared.plate import normalize_plate
    from datetime import datetime, timedelta, timezone as tz
    from app.modules.parking.models import ParkingSpace

    result: dict = {"units": [], "residents": [], "vehicles": [], "yard_spaces": [], "buried_spaces": []}

    cx = (await db.execute(select(Complex))).scalars().first()
    if cx is None:
        cx = Complex(code="ORKID", name="مجتمع ارکیده"); db.add(cx); await db.flush()
    tw = (await db.execute(select(Tower).where(Tower.code == "T1"))).scalars().first()
    if tw is None:
        tw = Tower(complex_id=cx.id, code="T1", name="برج ۱", floor_count=10, is_active=True)
        db.add(tw); await db.flush()

    persons_and_vehicles = [
        # (ساکن، پلاک‌ها) — پلاک سوم هر ساکن = خودروی دفنی
        ("علی", "رضایی",  "12ب345ایران11", "22د456ایران22", "32و567ایران33"),
        ("مریم", "کریمی", "43ه678ایران44", "54ز789ایران55", "65ح890ایران66"),
    ]

    for first, last, p1, p2, p3 in persons_and_vehicles:
        unit_number = f"{first}-{last}"[:12]
        unit = Unit(tower_id=tw.id, unit_number=unit_number, floor_number=1, is_active=True)
        db.add(unit); await db.flush()
        person = Person(first_name=first, last_name=last, person_type="OWNER", is_active=True)
        db.add(person); await db.flush()
        occ = UnitOccupancy(unit_id=unit.id, person_id=person.id, occupancy_type="OWNER",
                            is_primary=True, start_date=__import__("datetime").date.today())
        db.add(occ)
        result["units"].append(unit.unit_number)
        result["residents"].append(f"{first} {last}")

        for plate, location in ((p1, "own"), (p2, "yard"), (p3, "buried")):
            norm = normalize_plate(plate) or plate
            v = Vehicle(owner_person_id=person.id, unit_id=unit.id,
                        plate_raw=plate, plate_normalized=norm, is_active=True)
            db.add(v); await db.flush()
            if location == "own":
                # مجوز ورود به پارکینگ خودش (مسقف)
                db.add(AccessPermit(vehicle_id=v.id, plate_normalized=norm, status="ACTIVE",
                                    permit_type="PERMANENT",
                                    valid_from=datetime.now(tz.utc) - timedelta(hours=1),
                                    valid_until=datetime.now(tz.utc) + timedelta(days=365)))
                # تخصیص به جایگاه مسقف ثابت
                sp = ParkingSpace(code=f"P-{unit_number}-{location}", parking_type="PRIVATE",
                                  zone="COVERED", floor=1, status="FREE", is_active=True)
                db.add(sp); await db.flush()
                db.add(ParkingAssignment(parking_space_id=sp.id, unit_id=unit.id, vehicle_id=v.id,
                                         assignment_type="PERMANENT", status="ACTIVE"))
            elif location == "yard":
                # ساکن متقاضی محوطه — مجوز بدون گیت خاص (در همهٔ گیت‌ها معتبر)
                db.add(AccessPermit(vehicle_id=v.id, plate_normalized=norm, status="ACTIVE",
                                    permit_type="TEMPORARY",
                                    valid_from=datetime.now(tz.utc) - timedelta(hours=1),
                                    valid_until=datetime.now(tz.utc) + timedelta(days=30)))
                result["yard_spaces"].append(norm)
            else:
                # دفنی — مجوز مسقف دیگر (طبقه پایین)
                db.add(AccessPermit(vehicle_id=v.id, plate_normalized=norm, status="ACTIVE",
                                    permit_type="PERMANENT",
                                    valid_from=datetime.now(tz.utc) - timedelta(hours=1),
                                    valid_until=datetime.now(tz.utc) + timedelta(days=365)))
                sp = ParkingSpace(code=f"B-{unit_number}-{location}", parking_type="PRIVATE",
                                  zone="BURIED", floor=-1, status="FREE", is_active=True)
                db.add(sp); await db.flush()
                db.add(ParkingAssignment(parking_space_id=sp.id, unit_id=unit.id, vehicle_id=v.id,
                                         assignment_type="PERMANENT", status="ACTIVE"))
                result["buried_spaces"].append(norm)
            result["vehicles"].append({"plate": norm, "location": location, "owner": f"{first} {last}"})

    # ۲ خودروی غریبه (بدون مجوز)
    # غریبه = پلاک شناخته‌شده ولی بدون مجوز (فعال) تا قانون بتواند تصمیم بگیرد؛
    # is_active=False می‌شد VEHICLE_INACTIVE و محافظ نرم‌کردن جلوی قانون را می‌گرفت.
    for plate in ("77ط123ایران77", "88ظ456ایران88"):
        norm = normalize_plate(plate) or plate
        v = Vehicle(plate_raw=plate, plate_normalized=norm, is_active=True)
        db.add(v); await db.flush()
        result["vehicles"].append({"plate": norm, "location": "unknown", "owner": "غریبه"})

    # قوانین نمونه (DRAFT — کارفرما از UI منتشر می‌کند)
    rules_seed = [
        EntryExitRule(name="ساکن → پارکینگ خودش", direction="IN", priority=10,
                      condition_mode="ALL",
                      conditions=[{"field": "has_valid_permit", "op": "true"}],
                      actions=[{"action": "allow_with_warning",
                                "params": {"reason": "RULE_RESIDENT_OWN"}}],
                      status="DRAFT"),
        EntryExitRule(name="متقاضی محوطه → بررسی اپراتور", direction="IN", priority=20,
                      condition_mode="ALL",
                      conditions=[{"field": "driver_request", "op": "eq", "value": "YARD"}],
                      actions=[{"action": "allow_with_warning",
                                "params": {"reason": "RULE_YARD_REQUEST"}},
                               {"action": "require_driver_selection"}],
                      status="DRAFT"),
        EntryExitRule(name="پلاک ناشناس → مرجوع به نگهبان", direction="IN", priority=90,
                      condition_mode="ALL",
                      conditions=[{"field": "has_valid_permit", "op": "false"}],
                      actions=[{"action": "refer_to_guard"}], status="DRAFT"),
    ]
    for r in rules_seed:
        db.add(r)
    result["rules_created"] = len(rules_seed)

    if user:
        await write_audit(db, user_id=user.id, action="SCENARIO_DEFAULT_SETUP", module="scenario",
                          entity_type="scenario", entity_id="default", new_values={"units": 2, "vehicles": 8})
    await db.commit()
    return {"success": True, **result}


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("settings.view"))):
    """شمارش کلید‌ها برای نمایش وضعیت فعلی."""
    from sqlalchemy import func
    counts = {}
    for name, model in [
        ("complexes", Complex), ("towers", Tower), ("units", Unit),
        ("residents", Person), ("vehicles", Vehicle), ("permits", AccessPermit),
        ("parking_spaces", ParkingSpace), ("sessions", ParkingSession),
        ("rules", EntryExitRule), ("users", _U),
    ]:
        counts[name] = int(await db.scalar(select(func.count()).select_from(model)) or 0)
    return counts
