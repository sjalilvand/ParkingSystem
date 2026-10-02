"""کاتالوگ مجوزهای ممیزی (§۸) — idempotent + تکمیل module/action (موج ۴b)."""
import asyncio

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.modules.identity.models import Permission

PERMS = [
    ("finance.view",         "finance",    "view",   "مشاهده اطلاعات مالی و بدهی‌ها"),
    ("finance.manage",       "finance",    "manage", "ایجاد تعرفه/اصلاحیه و مدیریت مالی"),
    ("finance.pay",          "finance",    "pay",    "ثبت پرداخت"),
    ("violations.view",      "violations", "view",   "مشاهده تخلفات"),
    ("violations.create",    "violations", "create", "ثبت تخلف"),
    ("violations.review",    "violations", "review", "تأیید/لغو تخلف و بررسی اعتراض"),
    ("parking.view",         "parking",    "view",   "مشاهده نقشه و وضعیت پارکینگ"),
    ("parking.manage",       "parking",    "manage", "مدیریت جایگاه‌ها و تخصیص"),
    ("gate.manual_access",   "gate",       "execute", "ورود/خروج دستی گیت"),
    ("gate.barrier_open",    "gate",       "execute", "بازکردن دستی راهبند"),
    ("roles.view",           "roles",      "view",   "مشاهده نقش‌ها و کاتالوگ مجوزها"),
    ("roles.create",         "roles",      "create", "ایجاد نقش"),
    ("roles.edit",           "roles",      "edit",   "ویرایش نقش و مجوزهای آن"),
    ("roles.delete",         "roles",      "delete", "حذف نقش بلااستفاده"),
    ("user.manage",          "identity",   "manage", "مدیریت کاربران"),
    ("settings.view",   "settings", "view",   "مشاهده تنظیمات و طراح‌ها"),
    ("settings.edit",   "settings", "edit",   "ویرایش تنظیمات/قبض/باکس/تعرفه‌پیش‌نویس"),
    ("settings.publish","settings", "publish","انتشار و بازگشت نسخه تنظیمات"),
    ("rules.view",      "rules",    "view",   "مشاهده قوانین ورود/خروج"),
    ("rules.edit",      "rules",    "edit",   "ایجاد و ویرایش قوانین"),
    ("rules.publish",   "rules",    "publish","تأیید و انتشار قوانین"),
    ("groups.view",     "groups",   "view",   "مشاهده گروه‌های خودرو"),
    ("groups.edit",     "groups",   "edit",   "مدیریت گروه‌های خودرو"),
]


async def main() -> None:
    cols = {c.name for c in Permission.__table__.columns}
    async with AsyncSessionLocal() as db:
        created = updated = 0
        for code, module, action, title in PERMS:
            p = (await db.execute(select(Permission).where(Permission.code == code))).scalar_one_or_none()
            if p is None:
                kwargs = {"code": code}
                if "title" in cols: kwargs["title"] = title
                if "description" in cols: kwargs["description"] = title
                if "module" in cols: kwargs["module"] = module
                if "action" in cols: kwargs["action"] = action
                db.add(Permission(**kwargs))
                created += 1
            else:
                changed = False
                if "module" in cols and getattr(p, "module", None) is None:
                    p.module = module; changed = True
                if "action" in cols and getattr(p, "action", None) is None:
                    p.action = action; changed = True
                if "title" in cols and getattr(p, "title", None) is None:
                    p.title = title; changed = True
                if changed: updated += 1
        await db.commit()
        print(f"created={created} updated={updated} catalog={len(PERMS)}")


if __name__ == "__main__":
    asyncio.run(main())

