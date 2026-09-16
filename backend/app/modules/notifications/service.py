from sqlalchemy.ext.asyncio import AsyncSession

from app.core.system_models import Notification
from app.realtime.manager import manager


async def push_notification(db: AsyncSession, *, recipient_user_id: str | None, title: str,
                            message: str | None = None, channel: str = "IN_APP",
                            payload: dict | None = None,
                            event: str = "notification.new") -> Notification:
    """ثبت اعلان در DB + push زنده WebSocket (recipient_user_id=None یعنی broadcast عمومی)."""
    obj = Notification(recipient_user_id=recipient_user_id, channel=channel,
                       title=title, message=message, payload=payload, status="SENT")
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    manager.broadcast_threadsafe(event, {
        "id": obj.id,
        "title": title,
        "message": message,
        "recipient_user_id": recipient_user_id,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        **(payload or {}),
    })
    return obj