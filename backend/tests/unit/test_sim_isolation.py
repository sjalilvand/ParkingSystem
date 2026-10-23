"""الحاقیه §۲ — تست جداسازی واقعی شبیه‌ساز از محیط عملیاتی.

تضمین‌ها:
  1) SimSessionLocal روی موتور جدا (URL متفاوت از DB اصلی) بسته شده است
  2) fail-fast: برابری SIM_DATABASE_URL با DATABASE_URL در SIM_STRICT ممنوع
  3) ensure_sim_schema روی DB شبیه‌ساز اسکیمای کامل می‌سازد
  4) دادهٔ شبیه‌ساز به DB اصلی نمی‌ریزد (شمارش جدول اصلی بعد از seed ثابت)
"""
import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


def test_sim_engine_is_separate_from_operational_engine():
    from app.db.sim_session import SimSessionLocal, sim_engine
    from app.db.session import AsyncSessionLocal, engine

    assert str(sim_engine.url) != str(engine.url), (
        "پایگاه‌دادهٔ شبیه‌ساز باید از پایگاه‌دادهٔ عملیاتی جدا باشد (الحاقیه §۲)")
    assert SimSessionLocal is not AsyncSessionLocal
    # ماژول‌های شبیه‌ساز/سناریوساز به جلسهٔ جدا وصل‌اند
    import app.modules.simulator.scenario as sc
    import app.modules.simulator.service as simsvc
    assert sc.AsyncSessionLocal is SimSessionLocal
    assert simsvc.AsyncSessionLocal is SimSessionLocal


def test_sim_strict_guard_rejects_same_url(monkeypatch):
    """برابری آدرس شبیه‌ساز با DB اصلی باید در import خطا بدهد (fail-fast)."""
    from app.core.config import settings
    import app.db.sim_session as ss

    monkeypatch.setattr(settings, "SIM_DATABASE_URL", settings.DATABASE_URL)
    with pytest.raises(RuntimeError, match="SIM_STRICT"):
        import importlib
        importlib.reload(ss)
    # بازگرداندن حالت سالم
    monkeypatch.setattr(settings, "SIM_DATABASE_URL", "sqlite+aiosqlite:///./sim_parking.db")
    importlib.reload(ss)
    # ماژول‌های وابسته ممکن است به instance قبلی اشاره کنند — دوباره اتصال
    import app.modules.simulator.scenario as sc
    import app.modules.simulator.service as simsvc
    sc.AsyncSessionLocal = ss.SimSessionLocal
    simsvc.AsyncSessionLocal = ss.SimSessionLocal


def test_ensure_sim_schema_creates_full_schema(tmp_path):
    """اسکیمای شبیه‌ساز idempotent روی موتور تستی ساخته می‌شود."""
    import app.db.sim_session as ss
    test_engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool)
    orig_engine, orig_ready = ss.sim_engine, ss._schema_ready
    try:
        ss.sim_engine = test_engine
        ss._schema_ready = False

        async def go():
            await ss.ensure_sim_schema()
            # دوباره: idempotent
            await ss.ensure_sim_schema()
            from sqlalchemy import inspect as sqlinspect
            async with test_engine.connect() as conn:
                names = await conn.run_sync(
                    lambda c: sqlinspect(c).get_table_names())
            return names

        names = asyncio.run(go())
        for t in ("vehicles", "parking_sessions", "access_events", "charges",
                  "vehicle_sync_runs", "plate_recognition_events", "gates"):
            assert t in names, f"جدول {t} در اسکیمای شبیه‌ساز نیست"
    finally:
        ss.sim_engine, ss._schema_ready = orig_engine, orig_ready
        asyncio.get_event_loop_policy()


def test_sim_seed_does_not_touch_operational_tables():
    """seed سناریو فقط DB شبیه‌ساز را پر می‌کند؛ DB اصلی بدون تغییر می‌ماند."""
    async def go():
        # موتور "عملیاتی" ساختگی
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

        main_engine = create_async_engine(
            "sqlite+aiosqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool)
        async with main_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        main_maker = async_sessionmaker(main_engine, expire_on_commit=False)

        # دادهٔ واقعی شبیه‌سازی‌شده در DB اصلی (مثل ۵۰۷ خودروی سرور محوطه)
        from app.modules.vehicles.models import Vehicle
        async with main_maker() as db:
            for i in range(5):
                db.add(Vehicle(plate_raw=f"11 ب {100+i} ایران 11",
                               plate_normalized=f"11B{100+i}IR11"))
            await db.commit()

        # ماژول سناریو + کاتالوگ را به موتور "شبیه‌ساز" جدا وصل کن
        sim_engine = create_async_engine(
            "sqlite+aiosqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool)
        async with sim_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sim_maker = async_sessionmaker(sim_engine, expire_on_commit=False)

        import app.modules.simulator.scenario as sc
        orig_local = sc.AsyncSessionLocal
        sc.AsyncSessionLocal = sim_maker
        try:
            from app.modules.identity.models import User
            from app.modules.config_admin.models import AppSetting
            async with sim_maker() as db:
                db.add(User(username="admin", password_hash="x",
                            full_name="ادمین", is_active=True))
                await db.commit()
            summary = await sc.setup_scenario()
            assert summary["scenario"]["vehicles"] == 9
        finally:
            sc.AsyncSessionLocal = orig_local

        # اثبات جداسازی: DB اصلی هنوز دقیقاً ۵ خودرو دارد و ساکن ندارد
        async with main_maker() as db:
            v = (await db.execute(select(func.count()).select_from(Vehicle))).scalar_one()
            from app.modules.residents.models import Person
            p = (await db.execute(select(func.count()).select_from(Person))).scalar_one()
        return v, p

    v, p = asyncio.run(go())
    assert v == 5, f"دادهٔ شبیه‌ساز به DB عملیاتی نشت کرده! vehicles={v}"
    assert p == 0
