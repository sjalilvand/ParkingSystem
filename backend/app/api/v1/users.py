from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.audit import write_audit
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import require_permission
from app.core.security import hash_password
from app.db.session import get_db
from app.modules.identity.models import (
    Permission,
    RefreshToken,
    Role,
    User,
    role_permissions,
    user_roles,
)

router = APIRouter(prefix="/users", tags=["Users"])
roles_router = APIRouter(prefix="/roles", tags=["Roles"])


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)
    full_name: str
    mobile: str | None = None
    role_codes: list[str] = []


class UserUpdate(BaseModel):
    full_name: str | None = None
    mobile: str | None = None


class RoleAssign(BaseModel):
    role_codes: list[str]


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8)


async def _role_codes_for(db: AsyncSession, user_id: str) -> list[str]:
    res = await db.execute(
        select(Role.code)
        .join(user_roles, user_roles.c.role_id == Role.id)
        .where(user_roles.c.user_id == user_id)
    )
    return list(res.scalars().all())


async def _user_payload(db: AsyncSession, u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "full_name": u.full_name,
        "mobile": u.mobile, "is_active": u.is_active, "is_locked": u.is_locked,
        "failed_login_count": u.failed_login_count,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "roles": await _role_codes_for(db, u.id),
    }


@router.get("")
async def list_users(
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user.manage")),
):
    query = select(User)
    if search:
        like = f"%{search}%"
        query = query.where(or_(User.username.ilike(like), User.full_name.ilike(like), User.mobile.ilike(like)))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = [await _user_payload(db, u) for u in result.scalars().all()]
    total_items = total or 0
    return {"items": items, "page": page, "page_size": page_size,
            "total_items": total_items, "total_pages": (total_items + page_size - 1) // page_size}


@router.post("")
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user.manage")),
):
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise ConflictError("نام کاربری تکراری است")

    roles: list[Role] = []
    if body.role_codes:
        roles = list((await db.execute(select(Role).where(Role.code.in_(body.role_codes)))).scalars().all())
        if len(roles) != len(set(body.role_codes)):
            raise NotFoundError("یکی از نقش‌های درخواستی یافت نشد")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        mobile=body.mobile,
    )
    db.add(user)
    await db.flush()
    for r in roles:
        await db.execute(user_roles.insert().values(user_id=user.id, role_id=r.id))
    if current_user:
        await write_audit(db, user_id=current_user.id, action="USER_CREATE", module="identity",
                          entity_type="user", entity_id=user.id,
                          new_values={"username": body.username, "roles": body.role_codes})
    await db.commit()
    await db.refresh(user)
    return await _user_payload(db, user)


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user.manage")),
):
    u = await db.get(User, user_id)
    if not u:
        raise NotFoundError("کاربر یافت نشد")
    return await _user_payload(db, u)


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user.manage")),
):
    u = await db.get(User, user_id)
    if not u:
        raise NotFoundError("کاربر یافت نشد")
    changed = {}
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(u, k, v)
            changed[k] = v
    if current_user:
        await write_audit(db, user_id=current_user.id, action="USER_UPDATE", module="identity",
                          entity_type="user", entity_id=u.id, new_values=changed)
    await db.commit()
    return await _user_payload(db, u)


@router.post("/{user_id}/activate")
async def activate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user.manage")),
):
    u = await db.get(User, user_id)
    if not u:
        raise NotFoundError("کاربر یافت نشد")
    u.is_active = True
    if current_user:
        await write_audit(db, user_id=current_user.id, action="USER_ACTIVATE", module="identity",
                          entity_type="user", entity_id=u.id)
    await db.commit()
    return {"success": True}


@router.post("/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user.manage")),
):
    if user_id == current_user.id:
        raise ForbiddenError("نمی‌توانید حساب خودتان را غیرفعال کنید")
    u = await db.get(User, user_id)
    if not u:
        raise NotFoundError("کاربر یافت نشد")
    u.is_active = False
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == u.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    if current_user:
        await write_audit(db, user_id=current_user.id, action="USER_DEACTIVATE", module="identity",
                          entity_type="user", entity_id=u.id)
    await db.commit()
    return {"success": True}


@router.post("/{user_id}/unlock")
async def unlock_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user.manage")),
):
    u = await db.get(User, user_id)
    if not u:
        raise NotFoundError("کاربر یافت نشد")
    u.is_locked = False
    u.failed_login_count = 0
    if current_user:
        await write_audit(db, user_id=current_user.id, action="USER_UNLOCK", module="identity",
                          entity_type="user", entity_id=u.id)
    await db.commit()
    return {"success": True}


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    body: PasswordReset,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user.manage")),
):
    u = await db.get(User, user_id)
    if not u:
        raise NotFoundError("کاربر یافت نشد")
    u.password_hash = hash_password(body.new_password)
    u.failed_login_count = 0
    # ابطال همه نشست‌های فعال کاربر (سند بخش ۲۴-۱)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == u.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    if current_user:
        await write_audit(db, user_id=current_user.id, action="USER_RESET_PASSWORD", module="identity",
                          entity_type="user", entity_id=u.id)
    await db.commit()
    return {"success": True}


@router.post("/{user_id}/roles")
async def assign_roles(
    user_id: str,
    body: RoleAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user.manage")),
):
    u = await db.get(User, user_id)
    if not u:
        raise NotFoundError("کاربر یافت نشد")

    roles: list[Role] = []
    if body.role_codes:
        roles = list((await db.execute(select(Role).where(Role.code.in_(body.role_codes)))).scalars().all())
        if len(roles) != len(set(body.role_codes)):
            raise NotFoundError("یکی از نقش‌های درخواستی یافت نشد")

    await db.execute(user_roles.delete().where(user_roles.c.user_id == u.id))
    for r in roles:
        await db.execute(user_roles.insert().values(user_id=u.id, role_id=r.id))
    if current_user:
        await write_audit(db, user_id=current_user.id, action="USER_ASSIGN_ROLES", module="identity",
                          entity_type="user", entity_id=u.id, new_values={"roles": body.role_codes})
    await db.commit()
    return await _user_payload(db, u)


@roles_router.get("")
async def list_roles(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("user.manage"))):
    rows = (await db.execute(
        select(Role, Permission)
        .join(role_permissions, role_permissions.c.role_id == Role.id, isouter=True)
        .join(Permission, Permission.id == role_permissions.c.permission_id, isouter=True)
        .order_by(Role.code)
    )).all()
    by_role: dict[str, dict] = {}
    for role, perm in rows:
        entry = by_role.setdefault(role.id, {
            "id": role.id, "code": role.code, "title": role.title,
            "description": role.description, "permissions": [],
        })
        if perm is not None:
            entry["permissions"].append({"code": perm.code, "title": perm.title, "module": perm.module})
    return list(by_role.values())


@roles_router.get("/permissions")
async def list_permissions(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("user.manage"))):
    result = await db.execute(select(Permission).order_by(Permission.module, Permission.code))
    return [{"id": p.id, "code": p.code, "title": p.title, "module": p.module} for p in result.scalars().all()]