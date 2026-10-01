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
    is_active: bool | None = None
    permission_codes: list[str] | None = None


def _role_out(db: AsyncSession, r: Role):
    async def _inner():
        perms = (await db.execute(
            select(Permission.code).join(role_permissions, role_permissions.c.permission_id == Permission.id)
            .where(role_permissions.c.role_id == r.id))).scalars().all()
        n_users = await db.scalar(select(func.count()).select_from(user_roles).where(
            user_roles.c.role_id == r.id))
        return {"id": r.id, "code": r.code, "name": r.name, "title": getattr(r, "title", r.name),
                "description": getattr(r, "description", None),
                "is_active": getattr(r, "is_active", True),
                "permissions": list(perms), "users_count": n_users or 0}
    return _inner


@router.get("")
async def list_roles(db: AsyncSession = Depends(get_db), user: User = Depends(
        require_permission("roles.view"))):
    roles = (await db.execute(select(Role).order_by(Role.name))).scalars().all()
    items = []
    for r in roles:
        perms = (await db.execute(
            select(Permission.code).join(role_permissions, role_permissions.c.permission_id == Permission.id)
            .where(role_permissions.c.role_id == r.id))).scalars().all()
        n = await db.scalar(select(func.count()).select_from(user_roles).where(user_roles.c.role_id == r.id))
        items.append({"id": r.id, "code": r.code, "name": r.name,
                      "description": getattr(r, "description", None),
                      "is_active": getattr(r, "is_active", True),
                      "permissions": list(perms), "users_count": n or 0})
    return items


@router.get("/permissions-catalog")
async def permissions_catalog(db: AsyncSession = Depends(get_db), user: User = Depends(
        require_permission("roles.view"))):
    rows = (await db.execute(select(Permission).order_by(Permission.module, Permission.action))).scalars().all()
    grouped: dict = {}
    for p in rows:
        grouped.setdefault(p.module, []).append(
            {"code": p.code, "action": p.action, "title": p.title})
    return grouped


@router.post("")
async def create_role(body: RoleCreate, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_permission("roles.create"))):
    dup = (await db.execute(select(Role).where(Role.code == body.code))).scalar_one_or_none()
    if dup:
        raise ConflictError("کد نقش تکراری است")
    r = Role(code=body.code, name=body.name, title=body.name,
             description=body.description, is_active=True)
    db.add(r)
    await db.flush()
    for pcode in body.permission_codes:
        p = (await db.execute(select(Permission).where(Permission.code == pcode))).scalar_one_or_none()
        if p:
            await db.execute(insert(role_permissions).values(role_id=r.id, permission_id=p.id))
    await write_audit(db, user_id=user.id, action="ROLE_CREATE", module="roles",
                      entity_type="role", entity_id=r.id, new_values={"code": body.code})
    await db.commit()
    return {"id": r.id, "code": r.code}


@router.patch("/{role_id}")
async def update_role(role_id: str, body: RoleUpdate, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_permission("roles.edit"))):
    r = await db.get(Role, role_id)
    if not r:
        raise NotFoundError("نقش یافت نشد")
    old = {"name": r.name, "is_active": getattr(r, "is_active", True)}
    if body.name is not None:
        r.name = body.name
        r.title = body.name
    if body.description is not None:
        r.description = body.description
    if body.is_active is not None:
        r.is_active = body.is_active
    if body.permission_codes is not None:
        await db.execute(role_permissions.delete().where(role_permissions.c.role_id == r.id)) \
            if hasattr(role_permissions, "delete") else None
        from sqlalchemy import delete as _del
        await db.execute(_del(role_permissions).where(role_permissions.c.role_id == r.id))
        for pcode in body.permission_codes:
            p = (await db.execute(select(Permission).where(Permission.code == pcode))).scalar_one_or_none()
            if p:
                await db.execute(insert(role_permissions).values(role_id=r.id, permission_id=p.id))
    await write_audit(db, user_id=user.id, action="ROLE_UPDATE", module="roles",
                      entity_type="role", entity_id=r.id,
                      old_values=old, new_values={"permissions": body.permission_codes})
    await db.commit()
    return {"success": True}


@router.delete("/{role_id}")
async def delete_role(role_id: str, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_permission("roles.delete"))):
    if r := await db.get(Role, role_id):
        if r.code == "ADMIN":
            raise ConflictError("نقش ادمین قابل حذف نیست")
        n = await db.scalar(select(func.count()).select_from(user_roles).where(user_roles.c.role_id == role_id))
        if n:
            raise ConflictError("این نقش به کاربران متصل است")
        from sqlalchemy import delete as _del
        await db.execute(_del(role_permissions).where(role_permissions.c.role_id == role_id))
        await db.delete(r)
        await write_audit(db, user_id=user.id, action="ROLE_DELETE", module="roles",
                          entity_type="role", entity_id=role_id)
        await db.commit()
    return {"success": True}


from sqlalchemy import insert  # noqa: E402