"""تست سناریوی آزمایشی شبیه‌ساز (موج ۱۰ + ۱۱) — پاکسازی + seed + ۳۲ گام در ۵ فاز + دستی.

فازها:
  ۱) محیط‌بندی و تردد پایه (ساکن/غریبه/ممنوعه/پلاک‌ناخوانا)
  ۲) فعال‌سازی قوانین و مقایسهٔ تصمیم‌ها (+ اثبات نرم‌نشدن ممنوعیت)
  ۳) ظرفیت محوطهٔ پر (YARD_CAPACITY_FULL) + ورود تکراری
  ۴) خروج با بدهی (D1=DENY مسدود، سپس WARN عبور با ثبت بدهی)
  ۵) جبران: لغو ممنوعیت + مجوز مهمان + خروج بدون نشست + خلاصه
"""
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
        # کاربر ادمین + تنظیمات کاربری + تنظیم سیاستیِ سناریو از اجرای قبل
        async with maker() as db:
            from app.modules.identity.models import User
            from app.modules.config_admin.models import AppSetting
            db.add(User(username="admin", password_hash="x", full_name="ادمین", is_active=True))
            db.add(AppSetting(key="user_note", value={"text": "بماند"}))
            db.add(AppSetting(key="yard_capacity", value={"total": 50}))
            db.add(AppSetting(key="gate_policy", value={"EXIT_UNPAID_POLICY": "DENY", "OTHER": 1}))
            await db.commit()
            # دادهٔ آلودهٔ پیش از پاکسازی
            from app.modules.complexes.models import Complex
            db.add(Complex(code="OLD", name="قدیمی"))
            await db.commit()

        sc = _patch_scenario(maker)
        out = await sc.setup_scenario()
        summ = out["scenario"]
        assert len(summ["residents"]) == 2, summ
        assert summ["vehicles"] == 9, summ  # ۶ ساکن + ۲ غریبه + ۱ ممنوعه
        assert summ["permits"] == 4, summ
        assert len(summ["draft_rules"]) == 3, summ
        assert summ["banned"] == ["BAN1"], summ
        assert summ["steps"] == 32, summ
        assert out["cleanup_deleted_rows"] >= 1  # مجتمع OLD پاک شده

        async with maker() as db:
            from app.modules.identity.models import User
            from app.modules.config_admin.models import AppSetting
            users = (await db.execute(select(User))).scalars().all()
            assert [u.username for u in users] == ["admin"]
            # تنظیمات کاربری می‌ماند اما کلیدهای سیاستیِ سناریو ریست می‌شوند
            note = (await db.execute(select(AppSetting).where(
                AppSetting.key == "user_note"))).scalar_one()
            assert note.value == {"text": "بماند"}
            yc = (await db.execute(select(AppSetting).where(
                AppSetting.key == "yard_capacity"))).scalar_one_or_none()
            assert yc is None  # ریست شد
            gp = (await db.execute(select(AppSetting).where(
                AppSetting.key == "gate_policy"))).scalar_one()
            assert gp.value == {"OTHER": 1}  # EXIT_UNPAID_POLICY حذف شد
            from app.modules.devices.models import Gate
            gates = (await db.execute(select(Gate))).scalars().all()
            assert {g.code for g in gates} == {"GATE-IN-01", "GATE-OUT-01"}
            from app.modules.vehicles.models import VehicleRestriction
            rest = (await db.execute(select(VehicleRestriction))).scalars().all()
            assert len(rest) == 1 and rest[0].status == "ACTIVE"

        # ── فاز ۱: محیط‌بندی و تردد پایه ──
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

        s7 = await sc.next_step()  # خودروی ممنوعه
        assert s7["result"]["decision"] == "DENY", s7["result"]
        assert s7["result"]["decision_reason"] == "PLATE_RESTRICTED"
        assert s7["result"]["barrier_action"] == "KEEP_CLOSED"
        assert any("BANNED" in x for x in s7["explanation"])

        s8 = await sc.next_step()
        assert s8["result"]["decision"] == "UNKNOWN_PLATE"
        assert s8["result"]["decision_reason"] == "PLATE_NOT_READABLE"

        # ── فاز ۲: فعال‌سازی قوانین ──
        s9 = await sc.next_step()
        assert s9["action"] == "activate_rule" and s9["rule"] == "R-SCEN-UNKNOWN"

        s10 = await sc.next_step()
        assert s10["result"]["decision"] == "REQUIRE_OPERATOR_APPROVAL", s10["result"]
        assert s10["result"]["decision_reason"] == "UNKNOWN_TO_GUARD"

        s11 = await sc.next_step()
        assert s11["rule"] == "R-SCEN-YARD"

        s12 = await sc.next_step()
        assert s12["result"]["decision"] == "REQUIRE_OPERATOR_APPROVAL", s12["result"]
        assert s12["result"]["decision_reason"] == "YARD_APPLICANT"

        s13 = await sc.next_step()
        assert s13["rule"] == "R-SCEN-RESIDENT"

        s14 = await sc.next_step()
        assert s14["result"]["decision"] == "ALLOW"
        assert s14["result"]["decision_reason"] == "EXIT_SESSION_CLOSED"

        s15 = await sc.next_step()  # ممنوعه با قوانین فعال — نرم نمی‌شود
        assert s15["result"]["decision"] == "DENY", s15["result"]
        assert s15["result"]["decision_reason"] == "PLATE_RESTRICTED"
        assert "RULE_SOFTEN_BLOCKED" in (s15["result"].get("warnings") or [])
        assert s15["result"].get("rule_trace", {}).get("rule_name")

        # ── فاز ۳: ظرفیت محوطهٔ پر ──
        s16 = await sc.next_step()
        assert s16["action"] == "set_yard_capacity" and s16["total"] == 2

        s17 = await sc.next_step()  # ALI3 — آخرین ظرفیت
        assert s17["result"]["decision"] == "ALLOW", s17["result"]
        assert s17["result"]["parking"]["code"] == "D-A-01"

        s18 = await sc.next_step()  # ALI1 — ظرفیت پر
        assert s18["result"]["decision"] == "REQUIRE_OPERATOR_APPROVAL", s18["result"]
        assert s18["result"]["decision_reason"] == "YARD_CAPACITY_FULL"
        assert s18["result"]["barrier_action"] == "KEEP_CLOSED"

        s19 = await sc.next_step()  # ورود تکراری MRY3
        assert s19["result"]["decision"] == "ALLOW_WITH_WARNING", s19["result"]
        assert s19["result"]["decision_reason"] == "DUPLICATE_ENTRY_SESSION_OPEN"

        s20 = await sc.next_step()
        assert s20["action"] == "clear_yard_capacity"

        s21 = await sc.next_step()  # ALI1 حالا عبور می‌کند
        assert s21["result"]["decision"] == "ALLOW", s21["result"]
        assert s21["result"]["decision_reason"] == "VALID_PERMIT"

        # ── فاز ۴: خروج با بدهی ──
        s22 = await sc.next_step()
        assert s22["action"] == "set_exit_policy" and s22["policy"] == "DENY"

        s23 = await sc.next_step()
        assert s23["action"] == "backdate_session" and s23["minutes"] == 90

        s24 = await sc.next_step()  # خروج مسدود
        assert s24["result"]["decision"] == "DENY", s24["result"]
        assert s24["result"]["decision_reason"] == "EXIT_UNPAID_BLOCKED"
        sess = s24["result"].get("session") or {}
        assert sess.get("final_amount", 0) > 0, sess
        assert "UNPAID_EXIT_BLOCKED_BY_POLICY" in (s24["result"].get("warnings") or [])

        s25 = await sc.next_step()
        assert s25["policy"] == "WARN"

        s26 = await sc.next_step()  # عبور با ثبت بدهی
        assert s26["result"]["decision"] == "ALLOW", s26["result"]
        assert s26["result"]["decision_reason"] == "EXIT_SESSION_CLOSED"
        assert "UNPAID_EXIT" in (s26["result"].get("warnings") or [])
        assert (s26["result"].get("session") or {}).get("payment_status") == "UNPAID"

        # ── فاز ۵: جبران و مهمان ──
        s27 = await sc.next_step()
        assert s27["action"] == "lift_restriction" and s27.get("lifted") == 1

        s28 = await sc.next_step()
        assert s28["action"] == "grant_permit" and s28["hours"] == 2

        s29 = await sc.next_step()  # ممنوعهٔ سابق با مجوز مهمان وارد می‌شود
        assert s29["result"]["decision"] == "ALLOW", s29["result"]
        assert s29["result"]["decision_reason"] == "VALID_PERMIT"

        s30 = await sc.next_step()
        assert s30["result"]["decision"] == "ALLOW"
        assert s30["result"]["decision_reason"] == "EXIT_SESSION_CLOSED"

        s31 = await sc.next_step()  # خروج بدون نشست باز
        assert s31["result"]["decision"] == "ALLOW_WITH_WARNING", s31["result"]
        assert s31["result"]["decision_reason"] == "NO_OPEN_SESSION_FOR_EXIT"

        s32 = await sc.next_step()
        assert s32["action"] == "summary"
        assert len(s32["explanation"]) >= 4
        assert s32["phase"] == "RECOVERY"

        fin = await sc.next_step()
        assert fin.get("finished") is True

        # بدهی ثبت شده؟ (فاز ۴ — Charge UNPAID برای خروجِ WARN با بدهی ALI1)
        # توجه: خروجِ BAN1 در همان ثانیه است → مدت ۰ → رایگان (بدون Charge)
        async with maker() as db:
            from app.modules.finance.models import Charge
            charges = (await db.execute(select(Charge).where(
                Charge.status == "UNPAID"))).scalars().all()
            assert len(charges) >= 1, len(charges)
            assert all(c.amount > 0 for c in charges)

        # ── وضعیت سناریو ──
        st = await sc.scenario_state()
        assert len(st["residents"]) == 2
        assert len(st["strangers"]) == 2
        assert len(st["banned"]) == 1
        assert st["banned"][0]["restricted"] is False  # در فاز ۵ لغو شد
        assert st["banned"][0]["has_permit"] is True   # مجوز مهمان گرفت
        assert st["active_rules"] == 3 and st["draft_rules"] == 0
        assert st["inside_count"] == 2  # MRY3 و ALI3 هنوز داخل‌اند
        assert st["total_spaces"] == 4
        codes = {s["code"]: s for s in st["spaces"]}
        assert codes["D-B-02"]["status"] == "OCCUPIED"
        assert codes["D-A-01"]["status"] == "OCCUPIED"
        assert codes["P-A-101"]["status"] == "FREE"  # بعد از خروج آزاد شد
        assert st["exit_policy"] == "WARN"
        assert st["yard_capacity"] is None
        assert st["tariff_active"] is True
        assert len(st["phases"]) == 5

        # ── رویداد دستی ──
        m = await sc.manual_event("12 ب 345 ایران 11", "IN")
        assert m["result"]["decision"] == "ALLOW", m["result"]
        assert m["role"] == "ALI1"
        m2 = await sc.manual_event("11 ک 111 ایران 55", "IN")  # ثبت‌نشده
        assert m2["result"]["decision"] == "REQUIRE_OPERATOR_APPROVAL"  # قانون ناشناس فعال است
        m3 = await sc.manual_event("", "IN")
        assert m3.get("error") == "PLATE_REQUIRED"

        # بازنشانی گام‌ها
        r = sc.reset_steps()
        assert r["step_index"] == 0 and r["total"] == 32

    asyncio.run(go())


def test_setup_is_repeatable():
    async def go():
        engine, maker = await _make_maker()
        sc = _patch_scenario(maker)
        await sc.setup_scenario()
        out2 = await sc.setup_scenario()  # بار دوم نباید خطای UNIQUE بدهد
        assert out2["scenario"]["vehicles"] == 9
        st = await sc.scenario_state()
        assert len(st["residents"]) == 2 and len(st["strangers"]) == 2
        assert len(st["banned"]) == 1 and st["banned"][0]["restricted"] is True

    asyncio.run(go())
