from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.system_models import Notification
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.notifications.service import push_notification

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _out(n: Notification) -> dict:
    return {
        "id": n.id, "title": n.title, "message": n.message, "channel": n.channel,
        "payload": n.payload, "status": n.status,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("")
async def list_notifications(page: int = 1, page_size: int = 20,
                             db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user)):
    query = select(Notification).where(
        or_(Notification.recipient_user_id == user.id, Notification.recipient_user_id.is_(None)))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await db.execute(
        query.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    unread = await db.scalar(select(func.count()).select_from(Notification).where(
        Notification.recipient_user_id == user.id, Notification.read_at.is_(None)))
    total_items = total or 0
    return {"items": [_out(n) for n in rows], "page": page, "page_size": page_size,
            "total_items": total_items, "total_pages": (total_items + page_size - 1) // page_size,
            "unread": unread or 0}


@router.get("/unread-count")
async def unread_count(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    c = await db.scalar(select(func.count()).select_from(Notification).where(
        or_(Notification.recipient_user_id == user.id, Notification.recipient_user_id.is_(None)),
        Notification.read_at.is_(None)))
    return {"unread": c or 0}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    n = await db.get(Notification, notification_id)
    if not n:
        raise NotFoundError("اعلان یافت نشد")
    if n.recipient_user_id and n.recipient_user_id != user.id:
        raise ForbiddenError("این اعلان متعلق به شما نیست")
    if n.read_at is None:
        n.read_at = datetime.now(timezone.utc)
        await db.commit()
    return {"success": True}


@router.post("/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await db.execute(update(Notification).where(
        or_(Notification.recipient_user_id == user.id, Notification.recipient_user_id.is_(None)),
        Notification.read_at.is_(None)
    ).values(read_at=datetime.now(timezone.utc)))
    await db.commit()
    return {"success": True}


@router.post("/test")
async def test_notification(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """ارسال اعلان آزمایشی به خود کاربر — برای تست push زنده WebSocket."""
    n = await push_notification(db, recipient_user_id=user.id,
                                title="اعلان آزمایشی", message="پیام زنده از سرور دریافت شد 🎉")
    return _out(n)