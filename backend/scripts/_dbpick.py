"""دیتابیسی را انتخاب می‌کند که واقعاً اسکیمای برنامه (جدول vehicles) را دارد."""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _read_env_url() -> str:
    env_path = BACKEND_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    return "sqlite+aiosqlite:///parking_dev.db"


def _mask(url: str) -> str:
    return url.split("@")[-1] if "@" in url else url


async def _tables(url: str) -> list:
    from sqlalchemy import inspect as sqlinspect
    from sqlalchemy.ext.asyncio import create_async_engine
    eng = create_async_engine(url)
    try:
        async with eng.connect() as conn:
            return await conn.run_sync(lambda c: sorted(sqlinspect(c).get_table_names()))
    except Exception as exc:
        print(f"    ! connect failed [{_mask(url)}]: {type(exc).__name__}: {str(exc)[:120]}")
        return []
    finally:
        await eng.dispose()


async def pick_database():
    """برمی‌گرداند: (url, tables). اولویت: دیتابیسی که جدول vehicles را دارد."""
    primary = _read_env_url()
    print(f">>> DB from .env: {_mask(primary)}")
    t = await _tables(primary)
    print(f"    tables ({len(t)}): {t if len(t) <= 14 else t[:14] + ['...']}")
    if "vehicles" in t:
        return primary, t

    sqlite_url = f"sqlite+aiosqlite:///{(BACKEND_DIR / 'parking_dev.db').as_posix()}"
    if (BACKEND_DIR / "parking_dev.db").exists():
        t2 = await _tables(sqlite_url)
        print(f">>> fallback SQLite parking_dev.db: tables ({len(t2)})")
        if "vehicles" in t2:
            print("    >>> switching to SQLite (app data lives here)")
            return sqlite_url, t2

    return primary, t


def activate(url: str) -> None:
    """قبل از import ماژول‌های app صدا زده شود (env var بر .env اولویت دارد)."""
    os.environ["DATABASE_URL"] = url
    sys.modules.pop("app.core.config", None)
    sys.modules.pop("app.db.session", None)