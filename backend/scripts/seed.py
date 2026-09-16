import asyncio
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import insert, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.modules.access_control.models import ParkingSession  # noqa: E402
from app.modules.complexes.models import Complex, Tower, Unit  # noqa: E402
from app.modules.devices.models import Device, Gate  # noqa: E402
from app.modules.finance.models import Tariff  # noqa: E402
from app.modules.identity.models import (  # noqa: E402
    Permission,
    Role,
    User,
    role_permissions,
    user_roles,
)
from app.modules.parking.models import (  # noqa: E402
    ParkingAssignment,
    ParkingOccupancy,
    ParkingSpace,
)
from app.modules.residents.models import Person, UnitOccupancy  # noqa: E402
from app.modules.vehicles.models import AccessPermit, Vehicle  # noqa: E402
from app.modules.violations.models import ViolationType  # noqa: E402

ROLES = [
    ("SUPER_ADMIN", "مدیر ارشد سامانه"),
    ("SYSTEM_ADMIN", "مدیر سیستم"),
    ("COMPLEX_MANAGER", "مدیر مجتمع"),
    ("TOWER_MANAGER", "مدیر برج"),
    ("GATE_OPERATOR", "اپراتور گیت"),
    ("FIELD_OPERATOR", "مسئول محوطه"),
    ("FINANCE_OPERATOR", "اپراتور مالی"),
    ("SECURITY_OPERATOR", "اپراتور امنیت"),
    ("REPORT_VIEWER", "بیننده گزارش‌ها"),
    ("SUPPORT_OPERATOR", "اپراتور پشتیبانی"),
]

PERMISSIONS = [
    ("user.manage", "مدیریت کاربران", "identity"),
    ("vehicle.read", "مشاهده خودروها", "vehicles"),
    ("vehicle.create", "ثبت خودرو", "vehicles"),
    ("vehicle.update", "ویرایش خودرو", "vehicles"),
    ("permit.issue", "صدور مجوز", "permits"),
    ("permit.revoke", "لغو مجوز", "permits"),
    ("gate.manual_open", "بازکردن دستی راهبند", "gate"),
    ("payment.create", "ثبت پرداخت", "finance"),
    ("payment.refund", "استرداد پرداخت", "finance"),
    ("debt.adjust", "اصلاح بدهی", "finance"),
    ("violation.create", "ثبت تخلف", "violations"),
    ("violation.cancel", "ابطال تخلف", "violations"),
    ("report.financial", "گزارش مالی", "reports"),
]


async def seed():
    print(">>> create missing tables ...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print(">>> seeding data ...")
    async with AsyncSessionLocal() as db:
        roles = {}
        for code, title in ROLES:
            res = await db.execute(select(Role).where(Role.code == code))
            role = res.scalar_one_or_none()
            if role is None:
                role = Role(code=code, title=title)
                db.add(role)
            roles[code] = role

        perms = {}
        for code, title, module in PERMISSIONS:
            res = await db.execute(select(Permission).where(Permission.code == code))
            perm = res.scalar_one_or_none()
            if perm is None:
                perm = Permission(code=code, title=title, module=module)
                db.add(perm)
            perms[code] = perm
        await db.flush()

        super_admin = roles["SUPER_ADMIN"]
        existing_perm_ids = set((await db.execute(
            select(role_permissions.c.permission_id).where(role_permissions.c.role_id == super_admin.id)
        )).scalars().all())
        rows = [{"role_id": super_admin.id, "permission_id": p.id}
                for p in perms.values() if p.id not in existing_perm_ids]
        if rows:
            await db.execute(role_permissions.insert(), rows)

        res = await db.execute(select(User).where(User.username == settings.DEFAULT_ADMIN_USERNAME))
        admin = res.scalar_one_or_none()
        if admin is None:
            admin = User(
                username=settings.DEFAULT_ADMIN_USERNAME,
                password_hash=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
                full_name="مدیر سامانه",
                is_active=True,
            )
            db.add(admin)
            await db.flush()
            await db.execute(user_roles.insert().values(user_id=admin.id, role_id=super_admin.id))
            print(f">>> admin created: {settings.DEFAULT_ADMIN_USERNAME}")
        elif admin.is_locked:
            admin.is_locked = False
            admin.failed_login_count = 0

        comp = (await db.execute(select(Complex).where(Complex.code == "C1"))).scalar_one_or_none()
        if comp is None:
            comp = Complex(code="C1", name="مجتمع نمونه", address="تهران")
            db.add(comp)
            await db.flush()
            print(">>> complex C1 created")

        tower = (await db.execute(select(Tower).where(Tower.code == "T1"))).scalar_one_or_none()
        if tower is None:
            tower = Tower(complex_id=comp.id, code="T1", name="برج یک", floor_count=10)
            db.add(tower)
            await db.flush()
            print(">>> tower T1 created")

        units = (await db.execute(select(Unit).where(Unit.tower_id == tower.id))).scalars().all()
        if not units:
            for i in range(1, 6):
                db.add(Unit(tower_id=tower.id, unit_number=str(100 + i), floor_number=(i + 1) // 2))
            await db.flush()
            units = (await db.execute(select(Unit).where(Unit.tower_id == tower.id))).scalars().all()
            print(f">>> {len(units)} units created")

        unit1 = units[0]

        person = (await db.execute(select(Person).where(Person.national_code == "0012345678"))).scalar_one_or_none()
        if person is None:
            person = Person(national_code="0012345678", first_name="علی", last_name="محمدی",
                            mobile="09121234567", person_type="OWNER")
            db.add(person)
            await db.flush()
            print(">>> person created")

        occ = (await db.execute(select(UnitOccupancy).where(
            UnitOccupancy.person_id == person.id,
            UnitOccupancy.unit_id == unit1.id,
        ))).scalar_one_or_none()
        if occ is None:
            db.add(UnitOccupancy(unit_id=unit1.id, person_id=person.id,
                                 occupancy_type="OWNER", is_primary=True,
                                 start_date=date.today()))

        vehicle = (await db.execute(select(Vehicle).where(Vehicle.plate_normalized == "12B345IR67"))).scalar_one_or_none()
        if vehicle is None:
            vehicle = Vehicle(owner_person_id=person.id, unit_id=unit1.id,
                              plate_raw="۱۲ ب ۳۴۵ ایران ۶۷", plate_normalized="12B345IR67",
                              brand="پژو", model="207", color="سفید")
            db.add(vehicle)
            await db.flush()
            print(">>> vehicle 12B345IR67 created")

        permit = (await db.execute(select(AccessPermit).where(
            AccessPermit.plate_normalized == "12B345IR67",
            AccessPermit.status == "ACTIVE",
        ))).scalars().first()
        if permit is None:
            db.add(AccessPermit(
                vehicle_id=vehicle.id, plate_normalized="12B345IR67",
                host_unit_id=unit1.id, permit_type="PRIMARY",
                valid_until=datetime.now(timezone.utc) + timedelta(days=365),
                issued_by=admin.id, reason="خودروی اصلی واحد 101",
            ))
            print(">>> PRIMARY permit ensured")

        gate_in = (await db.execute(select(Gate).where(Gate.code == "GATE-IN-01"))).scalar_one_or_none()
        if gate_in is None:
            gate_in = Gate(complex_id=comp.id, code="GATE-IN-01", name="گیت ورودی", direction="IN")
            db.add(gate_in)
            await db.flush()
            db.add(Device(gate_id=gate_in.id, device_type="CAMERA", vendor="MOCK", model="MockCam-1", protocol="HTTP"))
            db.add(Device(gate_id=gate_in.id, device_type="BARRIER", vendor="MOCK", model="MockBarrier-1", protocol="RELAY"))
            print(">>> gate GATE-IN-01 + devices created")

        gate_out = (await db.execute(select(Gate).where(Gate.code == "GATE-OUT-01"))).scalar_one_or_none()
        if gate_out is None:
            gate_out = Gate(complex_id=comp.id, code="GATE-OUT-01", name="گیت خروجی", direction="OUT")
            db.add(gate_out)
            print(">>> gate GATE-OUT-01 created")

        spaces = (await db.execute(select(ParkingSpace).where(ParkingSpace.zone == "A"))).scalars().all()
        if not spaces:
            for i in range(1, 7):
                db.add(ParkingSpace(complex_id=comp.id, tower_id=tower.id,
                                    code=f"P-A-{i:03d}", number=str(i), floor=-1, zone="A"))
            await db.flush()
            print(">>> 6 parking spaces created")

        target_space = (await db.execute(select(ParkingSpace).where(ParkingSpace.code == "P-A-001"))).scalar_one()
        assignment = (await db.execute(select(ParkingAssignment).where(
            ParkingAssignment.parking_space_id == target_space.id,
            ParkingAssignment.status == "ACTIVE",
        ))).scalar_one_or_none()
        if assignment is None:
            db.add(ParkingAssignment(parking_space_id=target_space.id, unit_id=unit1.id,
                                     vehicle_id=vehicle.id, assignment_type="PERMANENT"))

        # ---- فاز ۷+۸: تعرفه و انواع تخلف ----
        tariff = (await db.execute(select(Tariff).where(Tariff.status == "ACTIVE"))).scalars().first()
        if tariff is None:
            db.add(Tariff(title="BASE-TARIFF", free_minutes=0, hourly_amount=10000,
                          daily_max_amount=500000, priority=1))
            print(">>> active tariff created (free=0min, hourly=10000, cap=500000)")

        for vcode, vpenalty in [
            ("WRONG_PARKING", 200000),
            ("BLOCKING_PATH", 300000),
            ("OVERSTAY_GUEST", 150000),
            ("NO_PERMIT", 100000),
        ]:
            vt = (await db.execute(select(ViolationType).where(ViolationType.code == vcode))).scalar_one_or_none()
            if vt is None:
                db.add(ViolationType(code=vcode, title=vcode, default_penalty_amount=vpenalty))
        print(">>> violation types ensured (4)")

        # ---- پاک‌سازی نشست‌های نیمه‌تمام برای تست تکرارپذیر ----
        for s in (await db.execute(select(ParkingSession).where(ParkingSession.status == "OPEN"))).scalars().all():
            s.status = "CANCELLED"
        for o in (await db.execute(select(ParkingOccupancy).where(ParkingOccupancy.status == "OCCUPIED"))).scalars().all():
            o.status = "VACATED"
            o.vacated_at = datetime.now(timezone.utc)
        for sp in (await db.execute(select(ParkingSpace).where(ParkingSpace.status == "OCCUPIED"))).scalars().all():
            sp.status = "FREE"

        await db.commit()

    print("OK - seed done (phase 7+8+9)")


if __name__ == "__main__":
    asyncio.run(seed())