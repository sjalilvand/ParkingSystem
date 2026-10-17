"""تست D7 — تسویه خروج با اعتبار پیش‌پرداخت در مهلت (SQLite درون‌حافظه، بدون سرویس خارجی)."""
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select


def _make_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool
    from app.db.base import Base
    # ایمپورت همه ماژول‌های مدل (هم‌تراز با integration helpers) تا create_all کامل شود
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
    return create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


async def _seed(engine, *, payment_amount: int, paid_minutes_ago: int):
    from app.modules.access_control.models import ParkingSession
    from app.modules.finance.models import Charge, Payment
    from app.db.session import AsyncSessionLocal  # noqa: F401  (import واقعی برای سازگاری)
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with maker() as db:
        session = ParkingSession(
            plate_normalized="12B345IR67", entry_at=now - timedelta(hours=2),
            status="OPEN", final_amount=30000, payment_status="UNPAID",
        )
        db.add(session)
        await db.flush()
        charge = Charge(parking_session_id=session.id, charge_type="PARKING",
                        amount=30000, paid_amount=0, status="UNPAID")
        payment = Payment(
            reference_number=f"PAY-D7-{payment_amount}-{paid_minutes_ago}",
            plate_normalized="12B345IR67", amount=payment_amount,
            payment_status="COMPLETED", paid_at=now - timedelta(minutes=paid_minutes_ago),
        )
        db.add_all([charge, payment])
        await db.commit()
        return session.id, now


async def _run_settle(engine, session_id: str, now, grace_minutes: int):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.modules.access_control.models import ParkingSession
    from app.modules.finance.models import Charge
    from app.modules.finance.service import settle_exit_with_prepaid_credit

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        session = await db.get(ParkingSession, session_id)
        result = await settle_exit_with_prepaid_credit(db, session, now, grace_minutes)
        await db.commit()
        charge = (await db.execute(
            select(Charge).where(Charge.parking_session_id == session_id)
        )).scalars().first()
        return result, session, charge


def test_d7_full_settlement_within_grace():
    from app.modules.finance.models import Charge

    async def go():
        engine = _make_engine()
        from app.db.base import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_id, now = await _seed(engine, payment_amount=35000, paid_minutes_ago=5)
        return await _run_settle(engine, session_id, now, grace_minutes=20)

    result, session, charge = asyncio.run(go())
    assert result is not None and result["settled"] is True
    assert result["credit_used"] == 30000  # فقط به اندازه بدهی تخصیص می‌یابد
    assert charge.status == "PAID"
    assert charge.paid_amount == 30000
    assert session.payment_status == "PAID"


def test_d7_partial_settlement_keeps_unpaid():
    from app.modules.finance.models import Charge

    async def go():
        engine = _make_engine()
        from app.db.base import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_id, now = await _seed(engine, payment_amount=10000, paid_minutes_ago=5)
        return await _run_settle(engine, session_id, now, grace_minutes=20)

    result, session, charge = asyncio.run(go())
    assert result is not None and result["settled"] is False
    assert result["credit_used"] == 10000
    assert charge.status == "UNPAID"
    assert charge.paid_amount == 10000
    assert session.payment_status == "UNPAID"


def test_d7_payment_beyond_grace_not_auto_allocated():
    from app.modules.finance.models import Charge

    async def go():
        engine = _make_engine()
        from app.db.base import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_id, now = await _seed(engine, payment_amount=35000, paid_minutes_ago=45)
        return await _run_settle(engine, session_id, now, grace_minutes=20)

    result, session, charge = asyncio.run(go())
    assert result is None
    assert charge.status == "UNPAID"
    assert charge.paid_amount == 0


def test_d7_zero_grace_disabled():
    async def go():
        engine = _make_engine()
        from app.db.base import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_id, now = await _seed(engine, payment_amount=35000, paid_minutes_ago=5)
        return await _run_settle(engine, session_id, now, grace_minutes=0)

    result, session, charge = asyncio.run(go())
    assert result is None
    assert charge.paid_amount == 0
