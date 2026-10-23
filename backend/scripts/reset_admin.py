"""ریست رمز + فعال‌سازی حساب ادمین در production:
    python -m scripts.reset_admin --password "NewPass@123"
(باید داخل کانتینر backend اجرا شود — دستور در راهنمای استقرار.)

علاوه بر رمز، این سه فیلد را هم اصلاح می‌کند تا پیام «حساب کاربری غیرفعال است»
یا «حساب کاربری قفل شده است» بعد از ریست دیده نشود:
    is_active=True, is_locked=False, failed_login_count=0
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def _reset(pw: str) -> None:
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.session import AsyncSessionLocal
    from app.modules.identity.models import User

    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
        if u is None:
            print("admin user not found")
            return
        u.password_hash = hash_password(pw)
        u.is_active = True
        u.is_locked = False
        u.failed_login_count = 0
        await db.commit()
        print(f"admin password UPDATED + account reactivated (is_active={u.is_active}, is_locked={u.is_locked})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--password", required=True)
    a = ap.parse_args()
    if len(a.password) < 8:
        print("password must be at least 8 characters")
        sys.exit(1)
    asyncio.run(_reset(a.password))


if __name__ == "__main__":
    main()
