"""Bootstrap نسخه production: create_all + ادمین + نقش ADMIN + گیت‌ها + جدول پلاک‌ها."""
import asyncio
import csv
import io
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

CSV_PATH = BACKEND_DIR / "app" / "shared" / "data" / "iran_plates_full.csv"


def parse_regions(text):
    rows, seen = [], set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parts = next(csv.reader(io.StringIO(line)))
        except Exception:
            continue
        parts = [p.strip().strip('"').strip() for p in parts]
        parts = [p for p in parts if p]
        if len(parts) < 4:
            continue
        while len(parts) > 4 and parts[0].isdigit():
            parts.pop(0)
        if len(parts) != 4:
            continue
        code, prov, city, letters = parts
        if not code.isdigit() or len(code) > 2:
            continue
        if "کد" in prov or prov in ("استان", "آیدی"):
            continue
        if "تخصیص" in prov:
            continue
        letters = " ".join(letters.split())
        key = (code, city, letters)
        if key in seen:
            continue
        seen.add(key)
        rows.append((code, prov, city, letters))
    return rows


def _mk(model, **wanted):
    allowed = set(model.__table__.columns.keys())
    return model(**{k: v for k, v in wanted.items() if k in allowed})


async def main():
    import app.main  # noqa: F401  (ثبت همه مدل‌ها روی Base.metadata)
    from sqlalchemy import insert, inspect as sqlinspect, select, func
    from app.core.config import settings
    from app.core.security import hash_password
    from app.db.base import Base
    from app.db.session import AsyncSessionLocal, engine
    from app.modules.complexes.models import Complex
    from app.modules.devices.models import Gate
    from app.modules.base_data.models import PlateRegion
    from app.modules.identity.models import Permission, Role, User, role_permissions, user_roles

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[bootstrap] schema create_all OK")

    async with AsyncSessionLocal() as db:
        # --- ادمین ---
        admin = (await db.execute(select(User).where(User.username == settings.DEFAULT_ADMIN_USERNAME))).scalar_one_or_none()
        if admin is None:
            admin = User(username=settings.DEFAULT_ADMIN_USERNAME,
                         password_hash=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
                         full_name="مدیر سیستم", is_active=True)
            db.add(admin)
            await db.flush()
            print(f"[bootstrap] admin user created: {admin.username}")
        else:
            print("[bootstrap] admin user exists")

        # --- نقش ADMIN + مجوز user.manage + اتصال ---
        role = (await db.execute(select(Role).where(Role.code == "ADMIN"))).scalar_one_or_none()
        if role is None:
            role = _mk(Role, code="ADMIN", name="مدیر سیستم", title="مدیر سیستم")
            db.add(role)
            await db.flush()
            print("[bootstrap] role ADMIN created")
        perm = (await db.execute(select(Permission).where(Permission.code == "user.manage"))).scalar_one_or_none()
        if perm is None:
            perm = _mk(Permission, code="user.manage", name="user.manage", title="مدیریت کاربران")
            db.add(perm)
            await db.flush()
            print("[bootstrap] permission user.manage created")
        exists = (await db.execute(select(role_permissions).where(
            role_permissions.c.role_id == role.id,
            role_permissions.c.permission_id == perm.id))).first()
        if exists is None:
            await db.execute(insert(role_permissions).values(role_id=role.id, permission_id=perm.id))
        exists = (await db.execute(select(user_roles).where(
            user_roles.c.user_id == admin.id, user_roles.c.role_id == role.id))).first()
        if exists is None:
            await db.execute(insert(user_roles).values(user_id=admin.id, role_id=role.id))

        # --- مجتمع + گیت‌های پیش‌فرض ---
        cx = (await db.execute(select(Complex))).scalars().first()
        if cx is None:
            cx = Complex(code="CMP-1", name="مجتمع پیش‌فرض")
            db.add(cx)
            await db.flush()
            print("[bootstrap] default complex created")
        for code, name, direction in (("GATE-IN-01", "گیت ورودی", "IN"),
                                      ("GATE-OUT-01", "گیت خروجی", "OUT")):
            g = (await db.execute(select(Gate).where(Gate.code == code))).scalar_one_or_none()
            if g is None:
                db.add(Gate(complex_id=cx.id, code=code, name=name, direction=direction, status="OFFLINE"))
                print(f"[bootstrap] gate created: {code}")

        # --- جدول پلاک‌ها ---
        n = await db.scalar(select(func.count()).select_from(PlateRegion))
        if not n:
            if CSV_PATH.exists():
                rows = parse_regions(CSV_PATH.read_text(encoding="utf-8-sig"))
                db.add_all([PlateRegion(plate_code=c, province=p, city=ci, letters=ls)
                            for c, p, ci, ls in rows])
                print(f"[bootstrap] plate regions seeded: {len(rows)}")
            else:
                print("[bootstrap] WARN plate csv not found:", CSV_PATH)
        else:
            print(f"[bootstrap] plate regions already: {n}")

        await db.commit()

    await engine.dispose()
    print("[bootstrap] BOOTSTRAP OK")


if __name__ == "__main__":
    asyncio.run(main())