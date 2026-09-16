from sqlalchemy.ext.asyncio import AsyncSession

from app.core.system_models import AuditLog


async def write_audit(db: AsyncSession, *, user_id: str | None, action: str, module: str,
                      entity_type: str | None = None, entity_id: str | None = None,
                      old_values: dict | None = None, new_values: dict | None = None,
                      ip_address: str | None = None, reason: str | None = None):
    db.add(AuditLog(
        user_id=user_id, action=action, module=module,
        entity_type=entity_type, entity_id=entity_id,
        old_values=old_values, new_values=new_values,
        ip_address=ip_address, reason=reason,
    ))