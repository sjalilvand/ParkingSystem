"""کاتالوگ مجوزهای ممیزی (سند §۸) — idempotent. اجرا: python -m scripts.seed_audit_permissions"""
import asyncio

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.modules.identity.models import Permission

PERMS = [
    ("finance.view",    "مشاهده اطلاعات مالی و بدهی‌ها"),
    ("finance.manage",  "ایجاد تعرفه/اصلاحیه و مدیریت مالی"),
    ("finance.pay",     "ثبت پرداخت"),
    ("violations.view",   "مشاهده تخلفات"),
    ("violations.create", "ثبت تخلف"),
    ("violations.review", "تأیید/لغو تخلف و بررسی اعتراض"),
    ("parking.view",    "مشاهده نقشه و وضعیت پارکینگ"),
    ("parking.manage",  "مدیریت جایگاه‌ها و تخصیص"),
    ("gate.manual_access", "ورود/خروج دستی گیت"),
    ("gate.barrier_open",  "بازکردن دستی راهبند"),
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        cols = {c.name for c in Permission.__table__.columns}
        created = 0
        for code, title in PERMS:
            exists = (await db.execute(select(Permission).where(Permission.code == code))).scalar_one_or_none()
            if exists:
                continue
            kwargs = {"code": code}
            if "title" in cols:
                kwargs["title"] = title
            if "description" in cols:
                kwargs["description"] = title
            db.add(Permission(**kwargs))
            created += 1
        await db.commit()
        print(f"permissions created: {created} (total catalog: {len(PERMS)})")


if __name__ == "__main__":
    asyncio.run(main())
