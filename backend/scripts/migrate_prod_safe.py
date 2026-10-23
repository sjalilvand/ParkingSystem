"""مهاجرت امن production — جایگزین مطمئن «alembic upgrade head» هنگام بوت کانتینر.

سه سناریو را پوشش می‌دهد:
  ۱) پایگاه‌دادهٔ خالی (بدون alembic_version و بدون جدول vehicles)
     → alembic upgrade head (زنجیرهٔ کامل از baseline)
  ۲) جدول‌ها موجود ولی alembic_version نیست (پایگاه‌دادهٔ قدیمیِ create_all)
     → alembic stamp ae1f830b6c93 (آخرین head پیش از p0001) سپس upgrade head
       تا فقط مهاجرت‌های p0001..p0007 اعمال شود و خطای «جدول موجود» رخ ندهد.
  ۳) alembic_version موجود → alembic upgrade head (رفتار عادی)

اجرا:  python -m scripts.migrate_prod_safe     (از پوشهٔ backend، مثل داخل کانتینر)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# آخرین revision پیش از p0001 — برای stamp پایگاه‌داده‌های قدیمی بدون alembic_version
PRE_P0001_HEAD = "ae1f830b6c93"


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


def main() -> int:
    from alembic import command

    has_version, has_vehicles = _probe()
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
