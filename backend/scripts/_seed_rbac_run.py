"""Seed RBAC: کاتالوگ مجوزها + ۵ نقش اولیه + اتصال ادمین. idempotent."""
import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.main  # noqa: F401

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.modules.identity.models import Permission, Role, User, role_permissions, user_roles

# ماتریس: module -> [actions]
MATRIX = {
    "dashboard":     ["view"],
    "gate":          ["view", "create", "edit"],
    "structure":     ["view", "create", "edit", "delete"],
    "field":         ["view", "create", "edit", "delete", "approve", "reject"],
    "vehicles":      ["view", "create", "edit", "delete", "export", "sensitive"],
    "permits":       ["view", "create", "edit", "delete", "approve", "reject"],
    "parking":       ["view", "create", "edit", "delete"],
    "access_events": ["view", "create", "edit", "export", "sensitive"],
    "debts":         ["view", "export"],
    "violations":    ["view", "create", "edit", "delete", "approve", "reject"],
    "tariffs":       ["view", "create", "edit", "delete"],
    "base_data":     ["view", "create", "edit", "delete"],
    "reports":       ["view", "export"],
    "users":         ["view", "create", "edit", "delete"],
    "roles":         ["view", "create", "edit", "delete"],
    "ops":           ["view", "create", "edit"],
    "simulator":     ["view", "create"],
    "audit":         ["view", "export"],
}

ACTION_FA = {"view": "مشاهده", "create": "ایجاد", "edit": "ویرایش", "delete": "حذف",
             "approve": "تأیید", "reject": "رد", "print": "چاپ", "export": "خروجی",
             "sensitive": "اطلاعات حساس"}

MODULE_FA = {"dashboard": "داشبورد", "gate": "پنل گیت", "structure": "ساختار مجتمع",
             "field": "مسئول محوطه", "vehicles": "خودروها", "permits": "مجوزها",
             "parking": "پارکینگ", "access_events": "تردد", "debts": "بدهی‌ها",
             "violations": "تخلفات", "tariffs": "تعرفه‌ها", "base_data": "اطلاعات پایه",
             "reports": "گزارش‌ها", "users": "کاربران", "roles": "نقش‌ها",
             "ops": "مرکز عملیات", "simulator": "شبیه‌ساز", "audit": "تاریخچه فعالیت"}

ROLES = {
    "ADMIN": {"name": "ادمین", "desc": "دسترسی کامل", "perms": None},  # None = همه
    "GUARD_IN": {"name": "نگهبان ورودی", "desc": "ثبت ورود/خروج در گیت",
                 "perms": ["gate.view", "gate.create", "gate.edit",
                           "access_events.view", "access_events.create",
                           "vehicles.view", "dashboard.view"]},
    "YARD_MANAGER": {"name": "مسئول محوطه", "desc": "مدیریت محوطه‌های اختصاصی",
                     "perms": ["dashboard.view", "field.view", "field.create", "field.edit",
                               "parking.view", "access_events.view",
                               "vehicles.view", "violations.view", "violations.create"]},
    "BUILDING_OBSERVER": {"name": "ناظر بیرونی - مدیر ساختمان", "desc": "مشاهده و پیگیری ساختمان‌های اختصاصی",
                          "perms": ["dashboard.view", "reports.view", "reports.export",
                                    "access_events.view", "violations.view",
                                    "vehicles.view", "debts.view",
                                    "field.view", "field.approve", "field.reject"]},
    "PLAN_MANAGER": {"name": "مدیر طرح", "desc": "گزارش تجمیعی طرح",
                     "perms": ["dashboard.view", "reports.view", "reports.export",
                               "access_events.view", "debts.view", "violations.view",
                               "vehicles.view", "parking.view",
                               "field.view", "field.approve", "field.reject"]},
}


async def main():
    async with AsyncSessionLocal() as db:
        # --- permissions ---
        perm_map = {}
        for mod, actions in MATRIX.items():
            for act in actions:
                code = f"{mod}.{act}"
                p = (await db.execute(select(Permission).where(Permission.code == code))).scalar_one_or_none()
                if p is None:
                    p = Permission(code=code, title=f"{MODULE_FA.get(mod, mod)} — {ACTION_FA.get(act, act)}")
                    db.add(p)
                    await db.flush()
                perm_map[code] = p
        await db.commit()
        print(f"[rbac] permissions: {len(perm_map)}")

        # --- roles ---
        admin_user = (await db.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
        for code, spec in ROLES.items():
            r = (await db.execute(select(Role).where(Role.code == code))).scalar_one_or_none()
            if r is None:
                r = Role(code=code, name=spec["name"], title=spec["name"], description=spec["desc"])
                db.add(r)
                await db.flush()
                print(f"[rbac] role created: {code}")
            # permissions
            existing = set((await db.execute(
                select(role_permissions.c.permission_id).where(
                    role_permissions.c.role_id == r.id))).scalars().all())
            wanted = spec["perms"]
            for pcode in (perm_map.keys() if wanted is None else wanted):
                p = perm_map.get(pcode)
                if p and p.id not in existing:
                    await db.execute(insert(role_permissions).values(
                        role_id=r.id, permission_id=p.id))
            # ادمین -> کاربر admin
            if code == "ADMIN" and admin_user:
                ex = (await db.execute(select(user_roles).where(
                    user_roles.c.user_id == admin_user.id,
                    user_roles.c.role_id == r.id))).first()
                if ex is None:
                    await db.execute(insert(user_roles).values(user_id=admin_user.id, role_id=r.id))
        await db.commit()
        print("[rbac] ROLES SEED OK")


from sqlalchemy import insert  # noqa: E402

if __name__ == "__main__":
    asyncio.run(main())