"""تست سناریوی آزمایشی شبیه‌ساز — پاکسازی + seed + گام‌به‌گام + دستی (SQLite درون‌حافظه)."""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


async def _make_maker():
    from app.db.base import Base
    # ایمپورت همه ماژول‌های مدل تا create_all کامل شود
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
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _patch_scenario(maker):
    """اتصال ماژول سناریو به دیتابیس تست."""
    import app.modules.simulator.scenario as sc
    sc.AsyncSessionLocal = maker
    return sc


def test_setup_scenario_and_steps():
    async def go():
        engine, maker = await _make_maker()
        # کاربر ادمین + یک تنظیم — باید بعد از پاکسازی باقی بمانند
        async with maker() as db:
            from app.modules.identity.models import User
            from app.modules.config_admin.models import AppSetting
            db.add(User(username="admin", password_hash="x", full_name="ادمین", is_active=True))
            db.add(AppSetting(key="yard_capacity", value={"total": 50}))
            await db.commit()
            # دادهٔ آلودهٔ پیش از پاکسازی
            from app.modules.complexes.models import Complex
            db.add(Complex(code="OLD", name="قدیمی"))
            await db.commit()

        sc = _patch_scenario(maker)
        out = await sc.setup_scenario()
        summ = out["scenario"]
        assert len(summ["residents"]) == 2, summ
        assert summ["vehicles"] == 8, summ
        assert summ["permits"] == 4, summ
        assert len(summ["draft_rules"]) == 3, summ
        assert out["cleanup_deleted_rows"] >= 1  # مجتمع OLD پاک شده

        async with maker() as db:
            from app.modules.identity.models import User
            from app.modules.config_admin.models import AppSetting
            users = (await db.execute(select(User))).scalars().all()
            assert [u.username for u in users] == ["admin"]
            st = (await db.execute(select(AppSetting).where(
                AppSetting.key == "yard_capacity"))).scalar_one()
            assert st.value == {"total": 50}
            from app.modules.devices.models import Gate
            gates = (await db.execute(select(Gate))).scalars().all()
            assert {g.code for g in gates} == {"GATE-IN-01", "GATE-OUT-01"}

        # --- گام‌به‌گام ---
        s1 = await sc.next_step()
        assert s1["action"] == "gate" and s1["role"] == "ALI1"
        assert s1["result"]["decision"] == "ALLOW", s1["result"]
        assert s1["result"]["decision_reason"] == "VALID_PERMIT"
        assert s1["result"]["barrier_action"] == "OPEN"
        assert s1["result"]["parking"]["code"] == "P-A-101"

        s2 = await sc.next_step()
        assert s2["result"]["decision"] == "ALLOW"
        assert s2["result"]["decision_reason"] == "EXIT_SESSION_CLOSED"

        s3 = await sc.next_step()
        assert s3["result"]["decision"] == "UNKNOWN_PLATE", s3["result"]
        assert s3["result"]["decision_reason"] == "NO_ACTIVE_PERMIT"
        assert s3["result"]["barrier_action"] == "KEEP_CLOSED"

        s4 = await sc.next_step()
        assert s4["result"]["decision"] == "ALLOW"
        assert s4["result"]["parking"]["code"] == "P-B-102"

        s5 = await sc.next_step()
        assert s5["result"]["decision"] == "ALLOW"
        assert s5["result"]["parking"]["code"] == "D-B-02"  # دفنی

        s6 = await sc.next_step()
        assert s6["result"]["decision"] == "UNKNOWN_PLATE"
        assert s6["result"]["decision_reason"] == "NO_ACTIVE_PERMIT"

        s7 = await sc.next_step()
        assert s7["result"]["decision"] == "UNKNOWN_PLATE"
        assert s7["result"]["decision_reason"] == "PLATE_NOT_READABLE"

        s8 = await sc.next_step()
        assert s8["action"] == "activate_rule" and s8["rule"] == "R-SCEN-UNKNOWN"

        s9 = await sc.next_step()
        assert s9["result"]["decision"] == "REQUIRE_OPERATOR_APPROVAL", s9["result"]
        assert s9["result"]["decision_reason"] == "UNKNOWN_TO_GUARD"

        s10 = await sc.next_step()
        assert s10["rule"] == "R-SCEN-YARD"

        s11 = await sc.next_step()
        assert s11["result"]["decision"] == "REQUIRE_OPERATOR_APPROVAL", s11["result"]
        assert s11["result"]["decision_reason"] == "YARD_APPLICANT"

        s12 = await sc.next_step()
        assert s12["rule"] == "R-SCEN-RESIDENT"

        s13 = await sc.next_step()
        assert s13["result"]["decision"] == "ALLOW"
        assert s13["result"]["decision_reason"] == "EXIT_SESSION_CLOSED"

        s14 = await sc.next_step()
        assert s14["action"] == "summary"
        assert len(s14["explanation"]) >= 3

        fin = await sc.next_step()
        assert fin.get("finished") is True

        # --- وضعیت سناریو ---
        st = await sc.scenario_state()
        assert len(st["residents"]) == 2
        assert len(st["strangers"]) == 2
        assert st["active_rules"] == 3 and st["draft_rules"] == 0
        assert st["inside_count"] == 1  # MRY3 هنوز داخل است
        assert st["total_spaces"] == 4
        codes = {s["code"]: s for s in st["spaces"]}
        assert codes["D-B-02"]["status"] == "OCCUPIED"
        assert codes["P-A-101"]["status"] == "FREE"  # بعد از خروج آزاد شد

        # --- رویداد دستی ---
        m = await sc.manual_event("12 ب 345 ایران 11", "IN")
        assert m["result"]["decision"] == "ALLOW", m["result"]
        assert m["role"] == "ALI1"
        m2 = await sc.manual_event("11 ک 111 ایران 55", "IN")  # ثبت‌نشده
        assert m2["result"]["decision"] == "REQUIRE_OPERATOR_APPROVAL"  # قانون ناشناس فعال است
        m3 = await sc.manual_event("", "IN")
        assert m3.get("error") == "PLATE_REQUIRED"

        # بازنشانی گام‌ها
        r = sc.reset_steps()
        assert r["step_index"] == 0 and r["total"] == 14

    asyncio.run(go())


def test_setup_is_repeatable():
    async def go():
        engine, maker = await _make_maker()
        sc = _patch_scenario(maker)
        await sc.setup_scenario()
        out2 = await sc.setup_scenario()  # بار دوم نباید خطای UNIQUE بدهد
        assert out2["scenario"]["vehicles"] == 8
        st = await sc.scenario_state()
        assert len(st["residents"]) == 2 and len(st["strangers"]) == 2

    asyncio.run(go())
