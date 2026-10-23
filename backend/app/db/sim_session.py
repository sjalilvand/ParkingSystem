"""جداسازی واقعی محیط شبیه‌ساز از محیط عملیاتی (الحاقیه §۲).

قواعد سخت‌گیرانه:
  1) شبیه‌ساز فقط روی ``SIM_DATABASE_URL`` کار می‌کند و این آدرس نباید با
     ``DATABASE_URL`` محیط عملیاتی یکسان باشد (fail-fast هنگام import).
  2) اسکیمای شبیه‌ساز با ``create_all`` ساخته می‌شود (مستقل از Alembic) و
     idempotent است — هیچ migration ای روی DB اصلی اجرا نمی‌شود.
  3) فقط ماژول‌های ``simulator`` و ``scenario`` مجاز به استفاده از
     ``SimSessionLocal`` هستند؛ بقیهٔ سیستم باید از ``get_db`` اصلی استفاده کند.
  4) موتور قواعد و منطق تصمیم «مشترک» است (همان access_control.service)، اما
     دادهٔ شبیه‌سازی (خودرو، نشست، بدهی، تخلف، جایگاه، مجوز) کاملاً جدا است.
  5) کاربران/نقش‌ها/تنظیماتِ اپ در DB عملیاتی می‌مانند؛ باکس‌ها/صف‌های
     شبیه‌ساز (state در حافظهٔ فرایند شبیه‌ساز) هم مستقل‌اند.

برچسب الزامی UI روی هر صفحهٔ شبیه‌ساز:
  «آزمایشی ـ فاقد اعتبار مالی و عملیاتی» (SimBanner در فرانت‌اند).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def _norm(url: str | None) -> str:
    return (url or "").strip().rstrip("/")


_MAIN = _norm(settings.DATABASE_URL)
_SIM = _norm(settings.SIM_DATABASE_URL)

if getattr(settings, "SIM_STRICT", True) and _SIM and _SIM == _MAIN:
    raise RuntimeError(
        "SIM_STRICT: SIM_DATABASE_URL نباید با DATABASE_URL محیط عملیاتی یکسان باشد — "
        "شبیه‌ساز باید روی پایگاه‌دادهٔ جدا اجرا شود (الحاقیه §۲)."
    )

sim_engine: AsyncEngine = create_async_engine(_SIM, echo=False, pool_pre_ping=True)
SimSessionLocal = async_sessionmaker(sim_engine, expire_on_commit=False, class_=AsyncSession)

_schema_ready = False


def sim_db_label() -> str:
    """برچسب امن برای نمایش در UI/لاگ (بدون نشت پسورد)."""
    try:
        return sim_engine.url.render_as_string(hide_password=True)
    except Exception:
        return "(sim-db)"


async def ensure_sim_schema() -> None:
    """ساخت اسکیمای کامل شبیه‌ساز (idempotent) — مستقل از Alembic."""
    global _schema_ready
    if _schema_ready:
        return
    # ثبت همهٔ مدل‌ها (همان الگوی tests/integration/helpers.py)
    import app.core.system_models  # noqa: F401
    from app.db.base import Base
    from app.modules.access_control import models as _ac  # noqa: F401
    from app.modules.base_data import models as _bd  # noqa: F401
    from app.modules.complexes import models as _cx  # noqa: F401
    from app.modules.config_admin import models as _cfg  # noqa: F401
    from app.modules.devices import models as _dv  # noqa: F401
    from app.modules.finance import models as _fn  # noqa: F401
    from app.modules.identity import models as _id  # noqa: F401
    from app.modules.parking import cad_models as _cad, models as _pk  # noqa: F401
    from app.modules.residents import models as _rs  # noqa: F401
    from app.modules.vehicles import models as _vh  # noqa: F401
    from app.modules.violations import models as _vl  # noqa: F401
    from app.modules.vehicle_sync import models as _vs  # noqa: F401

    async with sim_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _schema_ready = True


async def get_sim_db() -> AsyncGenerator[AsyncSession, None]:
    """Depend جدا برای روت‌های سناریوساز/شبیه‌ساز (جای get_db اصلی)."""
    await ensure_sim_schema()
    async with SimSessionLocal() as session:
        yield session
