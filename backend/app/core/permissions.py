from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import ForbiddenError
from app.db.session import get_db
from app.modules.identity.models import Permission, Role, User, role_permissions, user_roles


async def user_has_permission(db: AsyncSession, user: User, perm_code: str) -> bool:
    result = await db.execute(
        select(Permission.id)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .join(user_roles, user_roles.c.role_id == role_permissions.c.role_id)
        .where(
            user_roles.c.user_id == user.id,
            Permission.code == perm_code,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def require_permission(perm_code: str):
    """وابستگی FastAPI: کاربر باید مجوز مشخصی داشته باشد (سند بخش ۲۴-۳)."""
    async def checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if await user_has_permission(db, user, perm_code):
            return user
        raise ForbiddenError("دسترسی مجاز نیست")
    return checker