"""CRUD نقش‌ها (سند §۸) — بر اساس اسکیمای واقعی:
Role(code, title, description) | Permission(code, title, module)
قرارداد API: name (ورودی/خروجی) به title نگاشت می‌شود؛ permissions = کد (رشته).
F25: نسخه قبلی با فیلدهای ناموجود (Role.name/Permission.action) نوشته شده بود و هرگز اجرا نمی‌شد."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.audit import write_audit
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.db.session import get_db
from app.modules.identity.models import (
    Permission, Role, User, role_permissions, user_roles,
)

router = APIRouter(prefix="/roles", tags=["Roles"])


class RoleCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    permission_codes: list[str] = []


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    permission_codes: list[str] | None = None


async def _permission_codes_for(db: AsyncSession, role_id: str) -> list[str]:
    res = await db.execute(
        select(Permission.code)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .where(role_permissions.c.role_id == role_id)
    )
    return list(res.scalars().all())


async def _users_count_for(db: AsyncSession, role_id: str) -> int:
    return await db.scalar(
        select(func.count()).select_from(user_roles).where(user_roles.c.role_id == role_id)
    ) or 0


async def _role_out(db: AsyncSession, r: Role) -> dict:
    return {
        "id": r.id, "code": r.code, "name": r.title, "title": r.title,
        "description": r.description, "is_active": True,
        "permissions": await _permission_codes_for(db, r.id),
        "users_count": await _users_count_for(db, r.id),
    }


@router.get("")
async def list_roles(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("roles.view"))):
    roles = (await db.execute(select(Role).order_by(Role.code))).scalars().all()
    return [await _role_out(db, r) for r in roles]


@router.get("/permissions-catalog")
async def permissions_catalog(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("roles.view"))):
    rows = (await db.execute(select(Permission).order_by(Permission.module, Permission.code))).scalars().all()
    grouped: dict = {}
    for p in rows:
        grouped.setdefault(p.module or "سایر", []).append({"code": p.code, "title": p.title})
    return grouped


@router.post("")
async def create_role(body: RoleCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("roles.create"))):
    code = (body.code or "").strip()
    name = (body.name or "").strip()
    if not code or not name:
        raise ConflictError("کد و نام نقش الزامی است")
    dup = (await db.execute(select(Role).where(Role.code == code))).scalar_one_or_none()
    if dup:
        raise ConflictError("کد نقش تکراری است")
    r = Role(code=code, title=name, description=body.description)
    db.add(r)
    await db.flush()
    for pcode in body.permission_codes:
        p = (await db.execute(select(Permission).where(Permission.code == pcode))).scalar_one_or_none()
        if p:
            await db.execute(role_permissions.insert().values(role_id=r.id, permission_id=p.id))
    if user:
        await write_audit(db, user_id=user.id, action="ROLE_CREATE", module="roles",
                          entity_type="role", entity_id=r.id,
                          new_values={"code": code, "permissions": body.permission_codes})
    await db.commit()
    return {"id": r.id, "code": r.code, "name": r.title}


@router.patch("/{role_id}")
async def update_role(role_id: str, body: RoleUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("roles.edit"))):
    r = await db.get(Role, role_id)
    if not r:
        raise NotFoundError("نقش یافت نشد")
    if body.name is not None:
        r.title = body.name.strip()
    if body.description is not None:
        r.description = body.description
    if body.permission_codes is not None:
        await db.execute(role_permissions.delete().where(role_permissions.c.role_id == r.id))
        for pcode in body.permission_codes:
            p = (await db.execute(select(Permission).where(Permission.code == pcode))).scalar_one_or_none()
            if p:
                await db.execute(role_permissions.insert().values(role_id=r.id, permission_id=p.id))
    if user:
        await write_audit(db, user_id=user.id, action="ROLE_UPDATE", module="roles",
                          entity_type="role", entity_id=r.id,
                          new_values={"name": body.name, "permissions": body.permission_codes})
    await db.commit()
    return {"success": True}


@router.delete("/{role_id}")
async def delete_role(role_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("roles.delete"))):
    r = await db.get(Role, role_id)
    if not r:
        raise NotFoundError("نقش یافت نشد")
    if r.code == "ADMIN":
        raise ConflictError("نقش ادمین قابل حذف نیست")
    if await _users_count_for(db, r.id):
        raise ConflictError("این نقش به کاربران متصل است")
    await db.execute(role_permissions.delete().where(role_permissions.c.role_id == r.id))
    await db.delete(r)
    if user:
        await write_audit(db, user_id=user.id, action="ROLE_DELETE", module="roles",
                          entity_type="role", entity_id=role_id)
    await db.commit()
    return {"success": True}
