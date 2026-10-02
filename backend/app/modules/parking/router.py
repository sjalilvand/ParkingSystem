from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.audit import write_audit
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_any_permission
from app.db.session import get_db
from app.modules.complexes.models import Tower, Unit
from app.modules.identity.models import User
from app.modules.parking.models import ParkingAssignment, ParkingOccupancy, ParkingSpace
from app.modules.parking.schemas import (
    ParkingAssignmentCreate,
    ParkingSpaceCreate,
    ParkingSpaceOut,
    ParkingSpaceUpdate,
)
from app.modules.vehicles.models import Vehicle
from app.capacity import count_confirmed_occupancy, yard_capacity_decision

router = APIRouter(tags=["Parking"])


def _perm(*codes: str):
    """F9: کنترل مجوز عملیات نوشتن پارکینگ — با ENFORCE_PARKING_PERMISSIONS قابل تعلیق."""
    if not getattr(settings, "ENFORCE_PARKING_PERMISSIONS", True):
        return get_current_user
    return require_any_permission(*codes)


@router.get("/parking/map")
async def parking_map(db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("parking.view"))):
    """نقشه پارکینگ: برج‌ها → طبقات → جایگاه‌ها (با پلاک خودروی حاضر)."""
    spaces = (await db.execute(
        select(ParkingSpace).where(ParkingSpace.is_active.is_(True))
    )).scalars().all()

    occs = (await db.execute(
        select(ParkingOccupancy).where(ParkingOccupancy.status == "OCCUPIED")
        .order_by(ParkingOccupancy.occupied_at.desc())
    )).scalars().all()

    occ_by_space: dict[str, object] = {}
    vehicle_ids: set[str] = set()
    for o in occs:
        if o.parking_space_id and o.parking_space_id not in occ_by_space:
            occ_by_space[o.parking_space_id] = o
            if o.vehicle_id:
                vehicle_ids.add(o.vehicle_id)

    vehicles: dict[str, Vehicle] = {}
    for vid in vehicle_ids:
        v = await db.get(Vehicle, vid)
        if v:
            vehicles[vid] = v

    def space_dto(s: ParkingSpace) -> dict:
        occ = occ_by_space.get(s.id)
        plate = None
        occupied_at = None
        if occ is not None:
            v = vehicles.get(occ.vehicle_id) if occ.vehicle_id else None
            if v:
                plate = v.plate_normalized
            occupied_at = occ.occupied_at.isoformat() if occ.occupied_at else None
        return {
            "id": s.id, "code": s.code, "floor": s.floor, "zone": s.zone,
            "parking_type": s.parking_type, "status": s.status,
            "plate": plate, "occupied_at": occupied_at,
        }

    towers = (await db.execute(select(Tower))).scalars().all()
    tower_by_id = {t.id: t for t in towers}

    tower_out: dict[str, dict] = {}
    buried: dict[int, list] = {}

    for s in spaces:
        dto = space_dto(s)
        if s.tower_id and s.tower_id in tower_by_id:
            t = tower_by_id[s.tower_id]
            entry = tower_out.setdefault(t.id, {
                "tower_id": t.id, "code": t.code, "name": t.name, "floors": {},
            })
        else:
            entry = buried.setdefault(-1, {"tower_id": None, "code": "BURIED",
                                           "name": "پارکینگ دفنی", "floors": {}})
        entry["floors"].setdefault(s.floor, []).append(dto)

    def finalize(entry: dict) -> dict:
        floors = [{"floor": f, "spaces": sorted(sp, key=lambda x: x["code"])}
                  for f, sp in sorted(entry["floors"].items(), reverse=True)]
        total = sum(len(f["spaces"]) for f in floors)
        occupied = sum(1 for f in floors for s in f["spaces"] if s["status"] == "OCCUPIED")
        return {**entry, "floors": floors, "total": total, "occupied": occupied}

    return {
        "towers": [finalize(e) for e in tower_out.values()],
        "buried": finalize(buried["-1"]) if "-1" in buried else None,
    }


@router.get("/parking-spaces")
async def list_spaces(zone: str | None = None, status: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("parking.view"))):
    query = select(ParkingSpace)
    if zone:
        query = query.where(ParkingSpace.zone == zone)
    if status:
        query = query.where(ParkingSpace.status == status)
    result = await db.execute(query.limit(500))
    return [ParkingSpaceOut.model_validate(s).model_dump() for s in result.scalars().all()]


@router.post("/parking-spaces")
async def create_space(body: ParkingSpaceCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("parking.manage"))):
    obj = ParkingSpace(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return ParkingSpaceOut.model_validate(obj).model_dump()


@router.get("/parking-spaces/{space_id}")
async def get_space(space_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("parking.view"))):
    obj = await db.get(ParkingSpace, space_id)
    if not obj:
        raise NotFoundError("پارکینگ یافت نشد")
    return ParkingSpaceOut.model_validate(obj).model_dump()


@router.patch("/parking-spaces/{space_id}")
async def update_space(space_id: str, body: ParkingSpaceUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("parking.manage"))):
    obj = await db.get(ParkingSpace, space_id)
    if not obj:
        raise NotFoundError("پارکینگ یافت نشد")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return ParkingSpaceOut.model_validate(obj).model_dump()


@router.post("/parking-assignments")
async def create_assignment(body: ParkingAssignmentCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("parking.manage"))):
    """F17 (§۱۱): تخصیص با اعتبارسنجی کامل — فضای موجود و بدون تخصیص فعال دیگر."""
    space = (await db.execute(
        select(ParkingSpace).where(ParkingSpace.id == body.parking_space_id).with_for_update()
    )).scalar_one_or_none()
    if not space:
        raise NotFoundError("پارکینگ یافت نشد")
    if not space.is_active:
        raise ConflictError("این جایگاه غیرفعال است")

    dup = (await db.execute(
        select(ParkingAssignment).where(
            ParkingAssignment.parking_space_id == body.parking_space_id,
            ParkingAssignment.status == "ACTIVE",
        )
    )).scalars().first()
    if dup:
        raise ConflictError("این جایگاه تخصیص فعال دارد",
                           details={"assignment_id": dup.id})

    if body.vehicle_id:
        v = await db.get(Vehicle, body.vehicle_id)
        if not v:
            raise NotFoundError("خودرو یافت نشد")
    if body.unit_id:
        u = await db.get(Unit, body.unit_id)
        if not u:
            raise NotFoundError("واحد یافت نشد")

    obj = ParkingAssignment(**body.model_dump())
    db.add(obj)
    if user:
        await write_audit(db, user_id=user.id, action="PARKING_ASSIGN", module="parking",
                          entity_type="parking_assignment", entity_id=obj.id,
                          new_values=body.model_dump())
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "status": obj.status}


@router.post("/parking-assignments/{assignment_id}/close")
async def close_assignment(assignment_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("parking.manage"))):
    obj = await db.get(ParkingAssignment, assignment_id)
    if not obj:
        raise NotFoundError("تخصیص یافت نشد")
    obj.status = "CLOSED"
    if user:
        await write_audit(db, user_id=user.id, action="PARKING_ASSIGN_CLOSE", module="parking",
                          entity_type="parking_assignment", entity_id=obj.id)
    await db.commit()
    return {"success": True}


@router.get("/parking-occupancies")
async def list_occupancies(status: str = "OCCUPIED", db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("parking.view"))):
    result = await db.execute(select(ParkingOccupancy).where(ParkingOccupancy.status == status).limit(500))
    return [{
        "id": o.id, "parking_space_id": o.parking_space_id, "vehicle_id": o.vehicle_id,
        "occupied_at": o.occupied_at.isoformat(), "status": o.status,
    } for o in result.scalars().all()]


@router.post("/parking-occupancies/{occupancy_id}/vacate")
async def vacate(occupancy_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("parking.manage"))):
    obj = await db.get(ParkingOccupancy, occupancy_id)
    if not obj:
        raise NotFoundError("اشغال یافت نشد")
    obj.status = "VACATED"
    obj.vacated_at = datetime.now(timezone.utc)
    if obj.parking_space_id:
        space = await db.get(ParkingSpace, obj.parking_space_id)
        if space:
            space.status = "FREE"
    if user:
        await write_audit(db, user_id=user.id, action="PARKING_VACATE", module="parking",
                          entity_type="parking_occupancy", entity_id=obj.id)
    await db.commit()
    return {"success": True}


@router.get("/parking/capacity-status")
async def capacity_status(db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("parking.view"))):
    """REQ-11-05/§۹: ظرفیت اعلامی در برابر حضور فیزیکی تأییدشده."""
    declared = getattr(settings, "YARD_CAPACITY_TOTAL", None)
    confirmed = await count_confirmed_occupancy(db)
    ok, reason = yard_capacity_decision(declared, confirmed)
    return {"declared_capacity": declared, "confirmed_presence": confirmed,
            "available": (declared - confirmed) if (declared or 0) > 0 else None,
            "accepting": ok, "reason": reason}


@router.post("/parking/capacity-mismatch")
async def capacity_mismatch(body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("parking.view"))):
    """REQ-11-05: ثبت مغایرت ظرفیت از سمت مسئول محوطه (اعلام انسانی) + اعلان."""
    observed = body.get("observed")
    system_count = await count_confirmed_occupancy(db)
    from app.modules.notifications.service import push_notification
    await push_notification(
        db, recipient_user_id=None,
        title="Capacity mismatch reported",
        message=f"observed={observed} system={system_count} note={body.get('note') or ''}",
        payload={"type": "CAPACITY_MISMATCH", "observed": observed, "system_count": system_count},
    )
    if user:
        await write_audit(db, user_id=user.id, action="CAPACITY_MISMATCH_REPORT", module="parking",
                          entity_type="parking", entity_id="yard",
                          new_values={"observed": observed, "system_count": system_count})
    await db.commit()
    return {"success": True, "system_count": system_count}

@router.get("/units/{unit_id}/parking-spaces")
async def unit_parking(unit_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_any_permission("parking.view"))):
    result = await db.execute(
        select(ParkingSpace)
        .join(ParkingAssignment, ParkingAssignment.parking_space_id == ParkingSpace.id)
        .where(ParkingAssignment.unit_id == unit_id, ParkingAssignment.status == "ACTIVE")
    )
    return [ParkingSpaceOut.model_validate(s).model_dump() for s in result.scalars().all()]

