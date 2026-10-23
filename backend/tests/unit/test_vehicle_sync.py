"""الحاقیه §۴ — تست همگام‌سازی Google Sheets (بدون شبکه؛ fetcher ساختگی).

پوشش:
  * ساخت خودرو از ردیف معتبر + ثبت نگاشت خارجی
  * پلاک نامعتبر / تاریخ نامعتبر → صف تعارض
  * کلید تکراری در شیت → تعارض DUPLICATE_KEY
  * به‌روزرسانی ردیف موجود (فقط فیلدهای مجاز)
  * PLATE_MISMATCH (همان پلاک، شناسهٔ دیگر) → تعارض، بدون ادغام خودکار
  * غیرتخریبی: محدودیت داخلی و بدهی دست‌نخورده می‌ماند
  * مجوز جدید برای خودروی sync-ساخته؛ تغییر مجوز موجود → PERMIT_CHANGE
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

HEADERS = ["external_vehicle_id", "source_system", "plate_raw", "plate_normalized",
           "owner_full_name", "owner_mobile", "unit_number", "tower_code",
           "brand", "model", "color", "year", "vehicle_type", "plate_type",
           "permit_type", "permit_valid_from", "permit_valid_until",
           "is_active", "notes", "external_updated_at"]


def _row(**kw):
    base = {c: "" for c in HEADERS}
    base.update(kw)
    return [base[c] for c in HEADERS]


async def _make_db():
    from app.db.base import Base
    from app.core import system_models  # noqa: F401
    from app.modules.config_admin import models as _cfg  # noqa: F401
    from app.modules.access_control import models as _ac  # noqa: F401
    from app.modules.base_data import models as _bd  # noqa: F401
    from app.modules.complexes import models as _cx  # noqa: F401
    from app.modules.devices import models as _dv  # noqa: F401
    from app.modules.finance import models as _fn  # noqa: F401
    from app.modules.identity import models as _id  # noqa: F401
    from app.modules.parking import cad_models as _cad, models as _pk  # noqa: F401
    from app.modules.residents import models as _rs  # noqa: F401
    from app.modules.vehicles import models as _vh  # noqa: F401
    from app.modules.violations import models as _vl  # noqa: F401
    from app.modules.vehicle_sync import models as _vs  # noqa: F401
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _run_sync(maker, rows, headers=HEADERS):
    """اجرای sync روی maker تستی با ردیف‌های ساختگی → (result, db_session)."""
    from app.modules.vehicle_sync.service import VehicleSyncService

    async def fetcher():
        return {"headers": headers, "rows": rows}

    async def go():
        async with maker() as db:
            svc = VehicleSyncService(db, fetcher=fetcher)
            result = await svc.run(trigger="MANUAL")
            return result, db
    return go


def test_vehicle_sync_full_flow():
    async def go():
        engine, maker = await _make_db()
        # دادهٔ محافظت‌شدهٔ پیش‌موجود: محدودیت داخلی + بدهی
        from app.modules.finance.models import Charge
        from app.modules.vehicles.models import Vehicle, VehicleRestriction
        async with maker() as db:
            v0 = Vehicle(plate_raw="34 ب 111 ایران 11", plate_normalized="34B111IR11")
            db.add(v0)
            await db.flush()
            db.add(VehicleRestriction(vehicle_id=v0.id,
                                      plate_normalized="34B111IR11",
                                      restriction_type="BANNED", status="ACTIVE"))
            db.add(Charge(amount=150000, charge_type="PARKING"))
            await db.commit()
            v0_id = v0.id

        rows = [
            # معتبر → ساخته می‌شود
            _row(external_vehicle_id="EXT-1", source_system="OPS",
                 plate_raw="12 ب 345 ایران 11", brand="پژو", model="206",
                 color="سفید", year="1399", vehicle_type="CAR",
                 plate_type="PERSONAL", is_active="فعال", notes="همگام"),
            # پلاک نامعتبر → تعارض
            _row(external_vehicle_id="EXT-2", source_system="OPS", plate_raw="سلام"),
            # تاریخ نامعتبر → تعارض
            _row(external_vehicle_id="EXT-3", source_system="OPS",
                 plate_raw="23 ص 456 ایران 22", permit_valid_until="نه"),
            # کلید تکراری → تعارض
            _row(external_vehicle_id="EXT-1", source_system="OPS",
                 plate_raw="45 د 789 ایران 33"),
        ]
        result, db = await _run_sync(maker, rows)()
        assert result["status"] in ("PARTIAL", "SUCCESS"), result
        st = result["stats"]
        assert st["rows_created"] == 1, st
        assert st["conflicts"] == 3, st

        # خودروی ساخته‌شده + نگاشت خارجی
        from app.modules.vehicle_sync.models import VehicleExternalRef, VehicleSyncConflict
        from app.modules.vehicles.models import Vehicle as V
        vs = (await db.execute(select(V))).scalars().all()
        assert len(vs) == 2  # v0 + ساخته‌شده
        created = next(v for v in vs if v.plate_normalized == "12B345IR11")
        assert created.brand == "پژو" and created.is_active is True
        assert created.notes.startswith("[SYNC:OPS:EXT-1]")
        refs = (await db.execute(select(VehicleExternalRef))).scalars().all()
        assert len(refs) == 1 and refs[0].external_vehicle_id == "EXT-1"

        # محافظت غیرتخریبی: محدودیت و بدهی دست‌نخورده
        rest = (await db.execute(select(VehicleRestriction))).scalars().all()
        assert len(rest) == 1 and rest[0].vehicle_id == v0_id
        ch = (await db.execute(select(Charge))).scalars().all()
        assert len(ch) == 1 and ch[0].amount == 150000

        # صف تعارض: ۳ مورد PENDING
        conf = (await db.execute(select(VehicleSyncConflict))).scalars().all()
        assert len(conf) == 3
        assert any(c.incoming and c.incoming.get("external_vehicle_id") == "EXT-2"
                   for c in conf)

        # ── اجرای دوم: همان کلید با تغییر مدل → updated ──
        rows2 = [
            _row(external_vehicle_id="EXT-1", source_system="OPS",
                 plate_raw="12 ب 345 ایران 11", brand="پژو", model="207",
                 color="سفید", is_active="فعال"),
        ]
        result2, db2 = await _run_sync(maker, rows2)()
        assert result2["stats"]["rows_updated"] == 1, result2
        v_new = (await db2.execute(
            select(V).where(V.plate_normalized == "12B345IR11"))).scalar_one()
        assert v_new.model == "207"

        # ── اجرای سوم: پلاک موجودِ سامانه با شناسهٔ دیگر → PLATE_MISMATCH ──
        rows3 = [
            _row(external_vehicle_id="EXT-9", source_system="OPS",
                 plate_raw="34 ب 111 ایران 11"),
        ]
        result3, db3 = await _run_sync(maker, rows3)()
        assert result3["stats"]["rows_skipped"] == 1, result3
        conf3 = (await db3.execute(select(VehicleSyncConflict).where(
            VehicleSyncConflict.status == "PENDING",
            VehicleSyncConflict.conflict_type == "PLATE_MISMATCH"))).scalars().all()
        assert len(conf3) == 1
        assert conf3[0].current.get("plate_raw") == "34 ب 111 ایران 11"

        # ── اجرای چهارم: مجوز روی خودروی دارای مجوز فعال → PERMIT_CHANGE ──
        from app.modules.vehicle_sync.models import VehicleSyncConflict as Conflict
        from app.modules.vehicles.models import AccessPermit
        rows4 = [
            _row(external_vehicle_id="EXT-1", source_system="OPS",
                 plate_raw="12 ب 345 ایران 11", permit_type="GUEST"),
        ]
        async with maker() as dbp:
            vp = (await dbp.execute(
                select(V).where(V.plate_normalized == "12B345IR11"))).scalar_one()
            dbp.add(AccessPermit(vehicle_id=vp.id, plate_normalized=vp.plate_normalized,
                                 permit_type="PERMANENT", status="ACTIVE"))
            await dbp.commit()
        result4, db4 = await _run_sync(maker, rows4)()
        conf4 = (await db4.execute(select(Conflict).where(
            Conflict.conflict_type == "PERMIT_CHANGE"))).scalars().all()
        assert len(conf4) >= 1, result4
        # مجوز داخلی دست‌نخورده (PERMANENT باقی مانده)
        perm = (await db4.execute(select(AccessPermit))).scalars().first()
        assert perm.permit_type == "PERMANENT"

    asyncio.run(go())


def test_jalali_date_and_bool_parsing():
    from app.modules.vehicle_sync.service import parse_any_date, parse_bool
    d = parse_any_date("1403-05-21")
    assert (d.year, d.month, d.day) == (2024, 8, 11)
    d2 = parse_any_date("2024/08/11")
    assert (d2.year, d2.month, d2.day) == (2024, 8, 11)
    assert parse_any_date("") is None
    assert isinstance(parse_any_date("بد"), str)
    assert parse_bool("فعال") is True
    assert parse_bool("غیرفعال") is False
    assert parse_bool("", True) is True


def test_rows_to_records_header_mapping():
    from app.modules.vehicle_sync.service import rows_to_records
    hdrs = ["plate_raw", "external_vehicle_id", "brand"]  # ترتیب عمداً متفاوت
    recs = rows_to_records(hdrs, [["12 ب 345 ایران 11", "K1", "پژو"]])
    assert recs[0]["external_vehicle_id"] == "K1"
    assert recs[0]["plate_raw"] == "12 ب 345 ایران 11"
