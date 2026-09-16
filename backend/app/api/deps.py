from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.modules.identity.models import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise UnauthorizedError("توکن ارائه نشده است")
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise UnauthorizedError("توکن نامعتبر است")
    if payload.get("type") != "access":
        raise UnauthorizedError("نوع توکن نامعتبر است")
    user = await db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise UnauthorizedError("کاربر یافت نشد یا غیرفعال است")
    return user