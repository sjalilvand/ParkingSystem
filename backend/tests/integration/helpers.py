"""Integration helpers - real isolated Postgres (parking_test_db).
کل session تست روی یک event loop پایدار اجرا می‌شود (ریشه‌حل خطای closed-loop)."""
import atexit
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

TEST_DB = "parking_test_db"
ADMIN_URL = "postgresql+asyncpg://parking:parking_pass@127.0.0.1:15432/postgres"
TEST_URL = f"postgresql+asyncpg://parking:parking_pass@127.0.0.1:15432/{TEST_DB}"
GATE_HEADERS = {"X-API-Key": "gate-dev-key"}

os.environ["DATABASE_URL"] = TEST_URL  # قبل از هر import اپ

# --- loop پایدار: همه‌چیز (seed، create_all، تست‌ها) روی همین loop ---
LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)


def run(coro):
    return LOOP.run_until_complete(coro)


def _pg_alive() -> bool:
    async def go():
        try:
            eng = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
            async with eng.connect():
                pass
            await eng.dispose()
            return True
        except Exception:
            return False
    return asyncio.run(go())  # engine موقتِ کوتاه‌عمر؛ loop جدا بی‌ضرر است


if not _pg_alive():
    import pytest
    pytest.skip("integration DB unavailable on 127.0.0.1:15432", allow_module_level=True)


def _ensure_test_db():
    async def go():
        eng = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
        async with eng.connect() as c:
            exists = (await c.execute(
                text("SELECT 1 FROM pg_database WHERE datname=:d"), {"d": TEST_DB})).scalar()
            if not exists:
                await c.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
        await eng.dispose()
    asyncio.run(go())


def _fresh_schema():
    async def go():
        eng = create_async_engine(TEST_URL, isolation_level="AUTOCOMMIT")
        async with eng.connect() as c:
            await c.execute(text("DROP SCHEMA public CASCADE"))
            await c.execute(text("CREATE SCHEMA public"))
        await eng.dispose()
    asyncio.run(go())


_ensure_test_db()
_fresh_schema()

from app.db.base import Base  # noqa: E402
from app.core import system_models  # noqa: E402,F401
from app.modules.config_admin import models as _cfg  # noqa: E402,F401
from app.modules.access_control import models as _ac  # noqa: E402,F401
from app.modules.base_data import models as _bd  # noqa: E402,F401
from app.modules.complexes import models as _cx  # noqa: E402,F401
from app.modules.devices import models as _dv  # noqa: E402,F401
from app.modules.finance import models as _fn  # noqa: E402,F401
from app.modules.identity import models as _id  # noqa: E402,F401
from app.modules.parking import cad_models as _cad, models as _pk  # noqa: E402,F401
from app.modules.residents import models as _rs  # noqa: E402,F401
from app.modules.vehicles import models as _vh  # noqa: E402,F401
from app.modules.violations import models as _vl  # noqa: E402,F401


def _create_all():
    async def go():
        eng = create_async_engine(TEST_URL)
        async with eng.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        await eng.dispose()
    run(go())


_create_all()

from app.core.security import hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402


def _fill_required(model, kwargs: dict) -> dict:
    """هر ستون required بدون default را با مقدار بی‌ضرر پر کن (مدل‌ها را حدس نمی‌زنیم)."""
    for c in model.__table__.columns:
        n = c.name
        if n in kwargs or c.primary_key or c.default is not None or c.server_default is not None:
            continue
        if c.nullable:
            continue
        t = str(c.type).upper()
        if "INT" in t:
            kwargs[n] = 0
        elif "BOOL" in t:
            kwargs[n] = True
        elif "TIMESTAMP" in t or "DATE" in t:
            kwargs[n] = datetime.now(timezone.utc)
        elif "FLOAT" in t or "NUMERIC" in t or "DOUBLE" in t:
            kwargs[n] = 0.0
        else:
            kwargs[n] = n
    return kwargs


async def _seed():
    from app.modules.devices.models import Gate
    from app.modules.finance.models import Tariff
    from app.modules.identity.models import Role, User, user_roles
    from app.modules.vehicles.models import AccessPermit, Vehicle

    async with AsyncSessionLocal() as db:
        db.add(Gate(**_fill_required(Gate, {"code": "GATE-IN-01", "name": "ورودی اصلی", "direction": "IN"})))
        for raw, norm in (("12ب345ایران67", "12B345IR67"), ("34د567ایران89", "34D567IR89")):
            db.add(Vehicle(**_fill_required(Vehicle, {
                "plate_raw": raw, "plate_normalized": norm, "is_active": True})))
            db.add(AccessPermit(**_fill_required(AccessPermit, {
                "plate_normalized": norm, "status": "ACTIVE", "permit_type": "PERMANENT",
                "max_entries": None})))
        db.add(Tariff(**_fill_required(Tariff, {
            "title": "test-tariff", "free_minutes": 60, "hourly_amount": 150_000,
            "daily_max_amount": None, "status": "ACTIVE"})))
        admin_role = Role(**_fill_required(Role, {"code": "ADMIN"}))
        limited_role = Role(**_fill_required(Role, {"code": "LIMITED"}))
        db.add_all([admin_role, limited_role])
        await db.flush()
        admin = User(**_fill_required(User, {
            "username": "admin", "password_hash": hash_password("Admin@1234"), "is_active": True}))
        op1 = User(**_fill_required(User, {
            "username": "op1", "password_hash": hash_password("Op@123456"), "is_active": True}))
        db.add_all([admin, op1])
        await db.flush()
        await db.execute(user_roles.insert().values(user_id=admin.id, role_id=admin_role.id))
        await db.execute(user_roles.insert().values(user_id=op1.id, role_id=limited_role.id))
        await db.commit()


run(_seed())




async def _seed_perms():
    from scripts.seed_audit_permissions import main as _main
    await _main()

run(_seed_perms())



async def _seed_config():
    from scripts.seed_config_defaults import main as _m
    await _m()

run(_seed_config())

@atexit.register
def _cleanup():
    """dispose روی همان loop پایدار — جلوگیری از نویز closed-loop هنگام خروج."""
    try:
        run(engine.dispose())
    except Exception:
        pass


@asynccontextmanager
async def api_client():
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.db.session import get_db

    async def _override_get_db():
        async with AsyncSessionLocal() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def login(ac, username: str, password: str) -> str:
    r = await ac.post("/api/v1/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


async def one_open_sessions(plate: str) -> int:
    from app.modules.access_control.models import ParkingSession
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(ParkingSession).where(
            ParkingSession.plate_normalized == plate, ParkingSession.status == "OPEN"))).scalars().all()
        return len(rows)
