"""مهاجرت امن production — جایگزین مطمئن «alembic upgrade head» هنگام بوت کانتینر.

سه سناریو را پوشش می‌دهد:
  ۱) پایگاه‌دادهٔ خالی (بدون alembic_version و بدون جدول vehicles)
     → alembic upgrade head (زنجیرهٔ کامل از baseline)
  ۲) جدول‌ها موجود ولی alembic_version نیست (پایگاه‌دادهٔ قدیمیِ create_all)
     → alembic stamp ae1f830b6c93 (آخرین head پیش از p0001) سپس upgrade head
       تا فقط مهاجرت‌های p0001..p0007 اعمال شود و خطای «جدول موجود» رخ ندهد.
  ۳) alembic_version موجود → alembic upgrade head (رفتار عادی)

علاوه بر این، آماده‌شدن پایگاه‌داده تا MIGRATE_DB_WAIT_SECONDS ثانیه (پیش‌فرض ۱۲۰)
منتظر می‌ماند تا اگر کانتینر postgres هنوز در حال راه‌اندازی بود، بوت بک‌اند
بی‌دلیل شکست نخورد. خطای پایدار هم با «نوع استثنا» چاپ می‌شود تا در docker logs
قابل تشخیص باشد (مثلاً InvalidPasswordError = ناهمخوانی رمز با volume موجود).

اجرا:  python -m scripts.migrate_prod_safe     (از پوشهٔ backend، مثل داخل کانتینر)
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# آخرین revision پیش از p0001 — برای stamp پایگاه‌داده‌های قدیمی بدون alembic_version
PRE_P0001_HEAD = "ae1f830b6c93"

DB_WAIT_SECONDS = int(os.environ.get("MIGRATE_DB_WAIT_SECONDS", "120"))
DB_RETRY_INTERVAL = 3


def _alembic_cfg():
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def _probe() -> tuple[bool, bool]:
    """(alembic_version موجود؟، vehicles موجود؟) — بدون خرابکاری."""
    from sqlalchemy import inspect
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import settings

    async def _run() -> tuple[bool, bool]:
        eng = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        try:
            def _has(sync_conn):
                insp = inspect(sync_conn)
                return (
                    insp.has_table("alembic_version"),
                    insp.has_table("vehicles"),
                )

            async with eng.connect() as conn:
                return await conn.run_sync(_has)
        finally:
            await eng.dispose()

    return asyncio.run(_run())


def _masked_db_url() -> str:
    """URL پایگاه‌داده بدون رمز — فقط برای لاگ تشخیصی."""
    from app.core.config import settings

    url = str(settings.DATABASE_URL)
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            return f"{scheme}://***@{rest.split('@', 1)[1]}"
    return url


def _probe_with_wait() -> tuple[bool, bool]:
    """تا آماده‌شدن پایگاه‌داده منتظر می‌ماند؛ خطای پایدار را با نوع استثنا گزارش می‌کند."""
    deadline = time.monotonic() + DB_WAIT_SECONDS
    attempt = 0
    last: Exception | None = None
    while True:
        attempt += 1
        try:
            return _probe()
        except Exception as exc:  # noqa: BLE001
            last = exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            print(
                f"[migrate] پایگاه‌داده هنوز آماده نیست ({type(exc).__name__}) — "
                f"تلاش {attempt}؛ {DB_RETRY_INTERVAL} ثانیه دیگر …",
                flush=True,
            )
            time.sleep(min(DB_RETRY_INTERVAL, max(1.0, remaining)))

    assert last is not None
    print(f"[migrate] ✗ اتصال به پایگاه‌داده پس از {attempt} تلاش ناموفق ماند:", flush=True)
    print(f"[migrate]   {type(last).__name__}: {last}", flush=True)
    print(f"[migrate]   هدف: {_masked_db_url()}", flush=True)
    if type(last).__name__ in (
        "InvalidPasswordError",
        "InvalidAuthorizationSpecificationError",
        "AuthenticationError",
        "CatalogsNotMatchingError",
    ):
        print(
            "[migrate]   ✚ رمز ناهمخوان: POSTGRES_PASSWORD در .env.prod با رمز اولیهٔ volume فرق دارد.",
            flush=True,
        )
        print(
            '[migrate]     راه‌حل سریع: docker compose -f docker-compose.prod.yml exec postgres '
            'psql -U parking -d parking_db -c "ALTER USER parking WITH PASSWORD \'رمز-جدید\';"',
            flush=True,
        )
    raise last


def main() -> int:
    from alembic import command

    has_version, has_vehicles = _probe_with_wait()
    cfg = _alembic_cfg()

    if has_version:
        print("[migrate] alembic_version موجود است → upgrade head")
    elif has_vehicles:
        print(
            f"[migrate] alembic_version نیست ولی جدول‌ها هستند → "
            f"stamp {PRE_P0001_HEAD} سپس upgrade head"
        )
        command.stamp(cfg, PRE_P0001_HEAD)
    else:
        print("[migrate] پایگاه‌دادهٔ خالی → upgrade head از baseline")

    command.upgrade(cfg, "head")
    print("[migrate] ✔ مهاجرت‌ها تا head اعمال شد")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
