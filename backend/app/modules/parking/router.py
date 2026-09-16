from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.complexes.models import Tower
from app.modules.identity.models import User
from app.modules.parking.models import ParkingAssignment, ParkingOccupancy, ParkingSpace
from app.modules.parking.schemas import (
    ParkingAssignmentCreate,
    ParkingSpaceCreate,
    ParkingSpaceOut,
    ParkingSpaceUpdate,
)
from app.modules.vehicles.models import Vehicle

router = APIRouter(tags=["Parking"])


@router.get("/parking/map")
async def parking_map(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
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
async def list_spaces(zone: str | None = None, status: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(ParkingSpace)
    if zone:
        query = query.where(ParkingSpace.zone == zone)
    if status:
        query = query.where(ParkingSpace.status == status)
    result = await db.execute(query.limit(500))
    return [ParkingSpaceOut.model_validate(s).model_dump() for s in result.scalars().all()]


@router.post("/parking-spaces")
async def create_space(body: ParkingSpaceCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = ParkingSpace(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return ParkingSpaceOut.model_validate(obj).model_dump()


@router.get("/parking-spaces/{space_id}")
async def get_space(space_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(ParkingSpace, space_id)
    if not obj:
        raise NotFoundError("پارکینگ یافت نشد")
    return ParkingSpaceOut.model_validate(obj).model_dump()


@router.patch("/parking-spaces/{space_id}")
async def update_space(space_id: str, body: ParkingSpaceUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(ParkingSpace, space_id)
    if not obj:
        raise NotFoundError("پارکینگ یافت نشد")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return ParkingSpaceOut.model_validate(obj).model_dump()


@router.post("/parking-assignments")
async def create_assignment(body: ParkingAssignmentCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = ParkingAssignment(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "status": obj.status}


@router.post("/parking-assignments/{assignment_id}/close")
async def close_assignment(assignment_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(ParkingAssignment, assignment_id)
    if not obj:
        raise NotFoundError("تخصیص یافت نشد")
    obj.status = "CLOSED"
    await db.commit()
    return {"success": True}


@router.get("/parking-occupancies")
async def list_occupancies(status: str = "OCCUPIED", db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(ParkingOccupancy).where(ParkingOccupancy.status == status).limit(500))
    return [{
        "id": o.id, "parking_space_id": o.parking_space_id, "vehicle_id": o.vehicle_id,
        "occupied_at": o.occupied_at.isoformat(), "status": o.status,
    } for o in result.scalars().all()]


@router.post("/parking-occupancies/{occupancy_id}/vacate")
async def vacate(occupancy_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(ParkingOccupancy, occupancy_id)
    if not obj:
        raise NotFoundError("اشغال یافت نشد")
    obj.status = "VACATED"
    obj.vacated_at = datetime.now(timezone.utc)
    if obj.parking_space_id:
        space = await db.get(ParkingSpace, obj.parking_space_id)
        if space:
            space.status = "FREE"
    await db.commit()
    return {"success": True}


@router.get("/units/{unit_id}/parking-spaces")
async def unit_parking(unit_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(
        select(ParkingSpace)
        .join(ParkingAssignment, ParkingAssignment.parking_space_id == ParkingSpace.id)
        .where(ParkingAssignment.unit_id == unit_id, ParkingAssignment.status == "ACTIVE")
    )
    return [ParkingSpaceOut.model_validate(s).model_dump() for s in result.scalars().all()]