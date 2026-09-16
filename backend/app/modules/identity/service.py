from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.modules.identity.models import RefreshToken, User
from app.modules.identity.schemas import TokenResponse

MAX_FAILED_LOGINS = 5


class AuthService:
    @staticmethod
    async def authenticate(db: AsyncSession, username: str, password: str) -> User:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if user is None:
            raise UnauthorizedError("نام کاربری یا رمز عبور نادرست است")

        if not verify_password(password, user.password_hash):
            user.failed_login_count += 1
            if user.failed_login_count >= MAX_FAILED_LOGINS:
                user.is_locked = True
            await db.commit()
            raise UnauthorizedError("نام کاربری یا رمز عبور نادرست است")

        if user.is_locked:
            raise UnauthorizedError("حساب کاربری قفل شده است؛ با مدیر تماس بگیرید")
        if not user.is_active:
            raise UnauthorizedError("حساب کاربری غیرفعال است")

        user.failed_login_count = 0
        user.last_login_at = datetime.now(timezone.utc)
        return user

    @staticmethod
    async def issue_tokens(db: AsyncSession, user: User, request: Request) -> TokenResponse:
        access_token = create_access_token(user.id, {"username": user.username})
        refresh_token, jti = create_refresh_token(user.id)
        db.add(RefreshToken(
            user_id=user.id,
            token_jti=jti,
            device_info=(request.headers.get("user-agent") or "")[:250],
            ip_address=request.client.host if request.client else None,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
        ))
        await db.commit()
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    async def rotate_refresh(db: AsyncSession, refresh_token: str, request: Request) -> TokenResponse:
        try:
            payload = decode_token(refresh_token)
        except Exception:
            raise UnauthorizedError("توکن refresh نامعتبر یا منقضی است")

        if payload.get("type") != "refresh":
            raise UnauthorizedError("نوع توکن نامعتبر است")

        result = await db.execute(select(RefreshToken).where(RefreshToken.token_jti == payload.get("jti")))
        stored = result.scalar_one_or_none()
        if stored is None or stored.revoked_at is not None:
            raise UnauthorizedError("نشست ابطال شده یا وجود ندارد")

        user = await db.get(User, payload.get("sub"))
        if user is None or not user.is_active:
            raise UnauthorizedError("کاربر یافت نشد یا غیرفعال است")

        stored.revoked_at = datetime.now(timezone.utc)
        return await AuthService.issue_tokens(db, user, request)