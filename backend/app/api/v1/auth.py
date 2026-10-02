from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token, hash_password, verify_password
from app.core.permissions import user_is_admin, user_permission_codes
from app.db.session import get_db
from app.modules.identity.models import RefreshToken, User, Role, user_roles
from app.modules.identity.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserOut,
)
from app.modules.identity.service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await AuthService.authenticate(db, body.username, body.password)
    return await AuthService.issue_tokens(db, user, request)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    return await AuthService.rotate_refresh(db, body.refresh_token, request)


@router.get("/me")
async def me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """اطلاعات کاربر جاری + نقش‌ها و مجوزهای مؤثر (سند §۸ — مبنای فیلتر منوی UI)."""
    roles = list((await db.execute(
        select(Role.code).join(user_roles, user_roles.c.role_id == Role.id)
        .where(user_roles.c.user_id == current_user.id)
    )).scalars().all())
    is_admin = await user_is_admin(db, current_user)
    perms = await user_permission_codes(db, current_user)
    return {
        "id": current_user.id, "username": current_user.username,
        "full_name": current_user.full_name, "mobile": current_user.mobile,
        "is_active": current_user.is_active,
        "last_login_at": current_user.last_login_at.isoformat() if current_user.last_login_at else None,
        "roles": roles, "permissions": perms, "is_admin": is_admin,
    }


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.password_hash):
        raise UnauthorizedError("رمز عبور فعلی نادرست است")
    current_user.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"success": True, "message": "رمز عبور با موفقیت تغییر کرد"}


@router.post("/logout")
async def logout(
    body: RefreshRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = decode_token(body.refresh_token)
        result = await db.execute(select(RefreshToken).where(RefreshToken.token_jti == payload.get("jti")))
        stored = result.scalar_one_or_none()
        if stored and stored.revoked_at is None:
            stored.revoked_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception:
        pass
    return {"success": True, "message": "خروج انجام شد"}