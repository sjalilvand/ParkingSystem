"""الحاقیه §۳ — تست پاکت ثبت پلاک + مسیر تأیید انسانی.

پوشش:
  * ارزیابی پاکت: زاویه/نور/سرعت خارج از محدوده → نقض
  * اطمینان پایین / پلاک ناشناس → NEEDS_REVIEW
  * قفل ایمنی گیت: خوانش کم‌اطمینانِ خودروی مجاز راهبند را خودکار باز نمی‌کند
  * صف بازبینی + اصلاح انسانی: مقدار اصلی حفظ، اصلاح جداگانه ثبت (کاربر+زمان)
"""
import asyncio
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


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


def test_envelope_evaluation():
    from app.modules.plate_ocr.envelope import evaluate_capture

    class FakeDB:
        async def execute(self, *_a, **_k):
            class R:
                def scalar_one_or_none(self):
                    return None
                def scalars(self):
                    return self
                def first(self):
                    return None
            return R()
    db = FakeDB()

    async def go():
        # داخل پاکت
        ok = await evaluate_capture(db, angle_deg=10, lux=100, speed_kmh=5,
                                    confidence=0.9, plate_normalized="12B345IR11")
        assert ok.ok and not ok.review_required, ok.as_dict()
        # زاویه/نور/سرعت خارج از پاکت
        bad = await evaluate_capture(db, angle_deg=60, lux=5, speed_kmh=60,
                                     confidence=0.9, plate_normalized="12B345IR11")
        assert not bad.ok and bad.review_required
        assert len(bad.violations) == 3
        assert any(v.startswith("ANGLE") for v in bad.violations)
        assert any(v.startswith("LUX") for v in bad.violations)
        assert any(v.startswith("SPEED") for v in bad.violations)
        # اطمینان پایین
        low = await evaluate_capture(db, confidence=0.2,
                                     plate_normalized="12B345IR11")
        assert low.review_required
        # پلاک ناشناس (ثبت‌نشده)
        unk = await evaluate_capture(db, confidence=0.9, plate_normalized=None)
        assert unk.review_required and not unk.ok
        # مقادیر None (سنسور ندارد) نقض نیست
        none_ok = await evaluate_capture(db, confidence=0.9,
                                         plate_normalized="12B345IR11")
        assert none_ok.ok

    asyncio.run(go())


def test_gate_blocks_auto_open_on_low_confidence():
    """خودروی مجاز اما با اطمینان پایین → REQUIRE_OPERATOR_APPROVAL (نه ALLOW)."""
    async def go():
        engine, maker = await _make_db()
        from app.core.config import settings
        from app.modules.devices.models import Gate
        from app.modules.vehicles.models import AccessPermit, Vehicle
        async with maker() as db:
            g_in = Gate(code="GATE-IN-01", name="ورودی", direction="IN")
            db.add(g_in)
            await db.flush()
            g_out = Gate(code="GATE-OUT-01", name="خروجی", direction="OUT")
            db.add(g_out)
            v = Vehicle(plate_raw="12 ب 345 ایران 11", plate_normalized="12B345IR11")
            db.add(v)
            await db.flush()
            db.add(AccessPermit(vehicle_id=v.id, plate_normalized="12B345IR11",
                                permit_type="PERMANENT", status="ACTIVE"))
            await db.commit()

        from app.modules.access_control.service import GateDecisionService
        async with maker() as db:
            res = await GateDecisionService.process_plate_event(
                db, gate_code="GATE-IN-01", direction="IN",
                plate_raw="12 ب 345 ایران 11", source_event_id="T-LOW-1",
                confidence=0.2,  # زیر آستانهٔ 0.55
                capture_quality={"angle_deg": 5, "lux": 120, "speed_kmh": 4},
            )
            assert res["decision"] == "REQUIRE_OPERATOR_APPROVAL", res
            assert res["decision_reason"] == "ENVELOPE_REVIEW_REQUIRED"
            assert res["plate_review"]["status"] == "NEEDS_REVIEW"
            assert res["barrier_action"] == "KEEP_CLOSED"

            # همان پلاک با اطمینان خوب → عبور عادی
            res2 = await GateDecisionService.process_plate_event(
                db, gate_code="GATE-OUT-01", direction="OUT",
                plate_raw="12 ب 345 ایران 11", source_event_id="T-OK-1",
                confidence=0.95,
                capture_quality={"angle_deg": 5, "lux": 120, "speed_kmh": 4},
            )
            assert res2["decision"] in ("ALLOW", "ALLOW_WITH_WARNING"), res2
            assert res2["plate_review"]["status"] == "AUTO_OK"
    asyncio.run(go())


def test_review_queue_and_correction_real():
    async def go():
        engine, maker = await _make_db()
        from app.modules.access_control.models import PlateRecognitionEvent
        from app.modules.devices.models import Gate
        from app.modules.identity.models import Role, user_roles
        async with maker() as db:
            g = Gate(code="GATE-IN-01", name="ورودی", direction="IN")
            db.add(g)
            await db.flush()
            rec = PlateRecognitionEvent(
                gate_id=g.id, direction="IN", plate_raw="پلاک نامفهوم",
                plate_normalized=None, confidence=0.31,
                source_event_id="SRC-R1", review_status="NEEDS_REVIEW")
            db.add(rec)
            role = Role(code="ADMIN", title="مدیر")
            from app.modules.identity.models import User
            db.add(role)
            await db.flush()
            u = User(username="op1", password_hash="x", full_name="اپراتور", is_active=True)
            db.add(u)
            await db.flush()
            await db.execute(user_roles.insert().values(user_id=u.id, role_id=role.id))
            await db.commit()
            rec_id, uid = rec.id, u.id

        from types import SimpleNamespace
        admin_like = SimpleNamespace(id=uid)
        from app.modules.access_control import router as gate_router

        async with maker() as db:
            # صف NEEDS_REVIEW
            listing = await gate_router.list_plate_reviews(
                status="NEEDS_REVIEW", limit=50, db=db, user=admin_like)
            assert listing["total"] == 1
            assert listing["items"][0]["id"] == rec_id

            # اصلاح انسانی
            out = await gate_router.resolve_plate_review(
                rec_id,
                gate_router.PlateReviewResolve(action="CORRECT",
                                               plate_raw="12 ب 345 ایران 11",
                                               note="اصلاح دستی نگهبان"),
                db=db, user=admin_like)
            assert out["success"] and out["review_status"] == "CORRECTED"
            assert out["plate_corrected_normalized"] == "12B345IR11"

            # اصل حفظ سابقه: مقدار اصلی + اصلاح + کاربر
            saved = await db.get(PlateRecognitionEvent, rec_id)
            assert saved.plate_raw == "پلاک نامفهوم"          # اصلی دست نخورد
            assert saved.plate_corrected == "12 ب 345 ایران 11"
            assert saved.corrected_by == uid
            assert saved.corrected_at is not None
            assert saved.correction_note == "اصلاح دستی نگهبان"

            # متریک‌ها
            metrics = await gate_router.plate_review_metrics(db=db, user=admin_like)
            assert metrics["counts"]["CORRECTED"] == 1
            assert metrics["counts"]["NEEDS_REVIEW"] == 0
    asyncio.run(go())
