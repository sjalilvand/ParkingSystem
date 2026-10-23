"""الحاقیه §۴ — APIهای همگام‌سازی و انطباق.

  /integrations/google-sheets       وضعیت/تست/اجرا (تنظیمات در env یا .env)
  /vehicle-sync/runs                تاریخچهٔ اجراها
  /vehicle-sync/conflicts           صف تعارض + تعیین تکلیف انسانی
  /compliance/vehicles              گزارش پوشش/انطباق دادهٔ خودروها
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.audit import write_audit
from app.core.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import user_has_permission, user_is_admin
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.vehicle_sync import sheet_client
from app.modules.vehicle_sync.models import VehicleExternalRef, VehicleSyncConflict, VehicleSyncRun
from app.modules.vehicle_sync.service import SHEET_COLUMNS, VehicleSyncService

router = APIRouter(tags=["Vehicle Sync"])


async def _perm_edit(db, user: User) -> None:
    if not (await user_is_admin(db, user) or await user_has_permission(db, user, "vehicles.edit")):
        raise ForbiddenError("مجوز ویرایش خودرو برای همگام‌سازی لازم است")


async def _perm_view(db, user: User) -> None:
    if not (await user_is_admin(db, user) or await user_has_permission(db, user, "vehicles.view")
            or await user_has_permission(db, user, "vehicles.edit")):
        raise ForbiddenError("مجوز مشاهدهٔ خودرو لازم است")


# ---------------------------------------------------------------------------
# /integrations/google-sheets
# ---------------------------------------------------------------------------
class SheetTestOut(BaseModel):
    pass


@router.get("/integrations/google-sheets/config")
async def sheets_config(user: User = Depends(get_current_user)):
    await _perm_view(db, user)
    sa_email = None
    try:
        sa_email = sheet_client.load_service_account().client_email
    except Exception as exc:  # noqa: BLE001
        sa_email = f"(تنظیم نشده: {exc})"
    return {
        "enabled": settings.GOOGLE_SHEETS_ENABLED,
        "spreadsheet_id": settings.GOOGLE_SHEETS_SPREADSHEET_ID,
        "worksheet": settings.GOOGLE_SHEETS_WORKSHEET,
        "service_account": sa_email,
        "sync_hour_tehran": settings.VEHICLE_SYNC_HOUR,
        "max_rows": settings.VEHICLE_SYNC_MAX_ROWS,
        "key_fields": ["source_system", "external_vehicle_id"],
        "columns": SHEET_COLUMNS,
        "readonly": True,
    }


@router.post("/integrations/google-sheets/test")
async def sheets_test(user: User = Depends(get_current_user)):
    await _perm_edit(db, user)
    return await sheet_client.test_connection()


@router.post("/integrations/google-sheets/run")
async def sheets_run_now(
    dry_run: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """اجرای دستی همگام‌سازی (روزی چندبار آزاد است؛ بدون تخریب)."""
    await _perm_edit(db, user)
    svc = VehicleSyncService(db)
    return await svc.run(trigger="MANUAL", operator_id=user.id, dry_run=dry_run)


# ---------------------------------------------------------------------------
# /vehicle-sync/runs
# ---------------------------------------------------------------------------
@router.get("/vehicle-sync/runs")
async def sync_runs(limit: int = Query(30, le=200),
                    db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    await _perm_view(db, user)
    rows = (await db.execute(select(VehicleSyncRun)
                             .order_by(VehicleSyncRun.started_at.desc())
                             .limit(limit))).scalars().all()
    return {"items": [{
        "id": r.id, "trigger": r.trigger, "status": r.status,
        "spreadsheet_id": r.spreadsheet_id, "worksheet": r.worksheet,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "rows_total": r.rows_total, "rows_created": r.rows_created,
        "rows_updated": r.rows_updated, "rows_skipped": r.rows_skipped,
        "conflicts_count": r.conflicts_count, "stats": r.stats, "error": r.error,
    } for r in rows]}


# ---------------------------------------------------------------------------
# /vehicle-sync/conflicts
# ---------------------------------------------------------------------------
class ConflictResolve(BaseModel):
    action: str = "SKIP"        # APPLY | SKIP
    note: str | None = None


@router.get("/vehicle-sync/conflicts")
async def sync_conflicts(status: str = "PENDING", limit: int = Query(50, le=200),
                         db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    await _perm_view(db, user)
    q = select(VehicleSyncConflict).where(VehicleSyncConflict.status == status.upper())
    total = (await db.execute(select(func.count()).select_from(VehicleSyncConflict)
                              .where(VehicleSyncConflict.status == status.upper()))).scalar_one()
    rows = (await db.execute(q.order_by(VehicleSyncConflict.created_at.desc())
                             .limit(limit))).scalars().all()
    return {"status": status.upper(), "total": total, "items": [{
        "id": c.id, "run_id": c.run_id, "row_number": c.row_number,
        "external_vehicle_id": c.external_vehicle_id,
        "source_system": c.source_system, "conflict_type": c.conflict_type,
        "message": c.message, "incoming": c.incoming, "current": c.current,
        "status": c.status, "resolved_by": c.resolved_by,
        "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
        "resolution_note": c.resolution_note,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    } for c in rows]}


@router.post("/vehicle-sync/conflicts/{conflict_id}/resolve")
async def resolve_conflict(conflict_id: str, body: ConflictResolve,
                           db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_user)):
    """تعیین تکلیف انسانی: APPLY (اعمال ردیف) یا SKIP (رد با یادداشت)."""
    await _perm_edit(db, user)
    c = await db.get(VehicleSyncConflict, conflict_id)
    if c is None:
        raise NotFoundError("تعارض یافت نشد")
    action = body.action.upper()
    if action not in ("APPLY", "SKIP"):
        raise ForbiddenError("عملیات نامعتبر (APPLY/SKIP)")
    applied = False
    if action == "APPLY":
        svc = VehicleSyncService(db)
        incoming = c.incoming or {}
        key = (str(c.source_system or "OPS"), str(c.external_vehicle_id or ""))
        if key[1] and not svc.validate_row_public(incoming):
            result = await svc._upsert_vehicle(incoming, key, c.run_id, c.row_number)  # noqa: SLF001
            applied = result in ("created", "updated")
    c.status = "RESOLVED_APPLIED" if (action == "APPLY" and applied) else "RESOLVED_SKIPPED"
    c.resolved_by = user.id
    c.resolved_at = datetime.now(timezone.utc)
    c.resolution_note = body.note
    await write_audit(db, user_id=user.id, action="VEHICLE_SYNC_CONFLICT_RESOLVE",
                      module="vehicle_sync", entity_type="vehicle_sync_conflict",
                      entity_id=c.id,
                      old_values={"status": "PENDING"},
                      new_values={"action": action, "applied": applied, "note": body.note})
    await db.commit()
    return {"success": True, "id": c.id, "status": c.status, "applied": applied}


# ---------------------------------------------------------------------------
# /compliance/vehicles — پوشش و انطباق
# ---------------------------------------------------------------------------
@router.get("/compliance/vehicles")
async def compliance_vehicles(db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)):
    """گزارش انطباق: پوشش sync، تعارض‌های باز، کلیدهای مبدأ بدون خودرو و..."""
    await _perm_view(db, user)
    from app.modules.vehicles.models import Vehicle

    total_vehicles = (await db.execute(select(func.count()).select_from(Vehicle))).scalar_one()
    mapped = (await db.execute(select(func.count()).select_from(VehicleExternalRef))).scalar_one()
    pending_conflicts = (await db.execute(
        select(func.count()).select_from(VehicleSyncConflict)
        .where(VehicleSyncConflict.status == "PENDING"))).scalar_one()
    runs_total = (await db.execute(select(func.count()).select_from(VehicleSyncRun))).scalar_one()
    last_run = (await db.execute(select(VehicleSyncRun)
                                 .order_by(VehicleSyncRun.started_at.desc())
                                 .limit(1))).scalars().first()
    return {
        "total_vehicles": total_vehicles,
        "externally_mapped": mapped,
        "unmapped": total_vehicles - mapped,
        "coverage_pct": round(100 * mapped / total_vehicles, 1) if total_vehicles else 0.0,
        "pending_conflicts": pending_conflicts,
        "runs_total": runs_total,
        "last_run": ({"id": last_run.id, "status": last_run.status,
                      "started_at": last_run.started_at.isoformat(),
                      "trigger": last_run.trigger} if last_run else None),
        "protected_domains": ["charges", "payments", "vehicle_restrictions",
                              "access_events", "parking_sessions",
                              "permits.max_entries/used_entries"],
    }
