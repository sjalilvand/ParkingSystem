from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.residents.models import Person, UnitOccupancy
from app.modules.residents.schemas import (
    OccupancyCreate,
    OccupancyOut,
    PersonCreate,
    PersonOut,
    PersonUpdate,
)

router = APIRouter(tags=["Residents"])


@router.get("/persons")
async def list_persons(search: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Person)
    if search:
        like = f"%{search}%"
        query = query.where(or_(Person.first_name.ilike(like), Person.last_name.ilike(like), Person.mobile.ilike(like)))
    result = await db.execute(query.limit(200))
    return [PersonOut.model_validate(p).model_dump() for p in result.scalars().all()]


@router.post("/persons")
async def create_person(body: PersonCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = Person(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return PersonOut.model_validate(obj).model_dump()


@router.get("/persons/{person_id}")
async def get_person(person_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Person, person_id)
    if not obj:
        raise NotFoundError("شخص یافت نشد")
    return PersonOut.model_validate(obj).model_dump()


@router.patch("/persons/{person_id}")
async def update_person(person_id: str, body: PersonUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Person, person_id)
    if not obj:
        raise NotFoundError("شخص یافت نشد")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return PersonOut.model_validate(obj).model_dump()


@router.delete("/persons/{person_id}")
async def delete_person(person_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.modules.vehicles.models import Vehicle

    obj = await db.get(Person, person_id)
    if not obj:
        raise NotFoundError("شخص یافت نشد")
    occ = await db.scalar(select(func.count()).select_from(
        select(UnitOccupancy.id).where(UnitOccupancy.person_id == person_id).subquery())) or 0
    veh = await db.scalar(select(func.count()).select_from(
        select(Vehicle.id).where(Vehicle.owner_person_id == person_id).subquery())) or 0
    if occ or veh:
        raise ConflictError(f"این شخص دارای ارجاع است (سکونت: {occ}، خودرو: {veh}) — ابتدا آن‌ها را حذف کنید")
    await db.delete(obj)
    await db.commit()
    return {"success": True}


@router.get("/units/{unit_id}/occupancies")
async def list_unit_occupancies(unit_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(UnitOccupancy, Person)
        .join(Person, Person.id == UnitOccupancy.person_id)
        .where(UnitOccupancy.unit_id == unit_id)
        .order_by(UnitOccupancy.created_at.desc())
    )).all()
    return [{
        "id": o.id, "person_id": p.id,
        "person_name": f"{p.first_name} {p.last_name}".strip(),
        "person_type": p.person_type, "mobile": p.mobile,
        "occupancy_type": o.occupancy_type,
        "start_date": o.start_date.isoformat(),
        "end_date": o.end_date.isoformat() if o.end_date else None,
        "is_primary": o.is_primary, "status": o.status,
    } for o, p in rows]


@router.post("/units/{unit_id}/occupancies")
async def create_occupancy(unit_id: str, body: OccupancyCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = UnitOccupancy(unit_id=unit_id, **body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return OccupancyOut.model_validate(obj).model_dump()


@router.patch("/occupancies/{occupancy_id}")
async def update_occupancy(occupancy_id: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(UnitOccupancy, occupancy_id)
    if not obj:
        raise NotFoundError("سابقه سکونت یافت نشد")
    for k in ("occupancy_type", "is_primary", "status"):
        if k in body:
            setattr(obj, k, body[k])
    await db.commit()
    await db.refresh(obj)
    return OccupancyOut.model_validate(obj).model_dump()


@router.delete("/occupancies/{occupancy_id}")
async def delete_occupancy(occupancy_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(UnitOccupancy, occupancy_id)
    if not obj:
        raise NotFoundError("سابقه سکونت یافت نشد")
    await db.delete(obj)
    await db.commit()
    return {"success": True}


@router.post("/occupancies/{occupancy_id}/close")
async def close_occupancy(occupancy_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(UnitOccupancy, occupancy_id)
    if not obj:
        raise NotFoundError("سابقه سکونت یافت نشد")
    obj.status = "CLOSED"
    obj.end_date = date.today()
    await db.commit()
    await db.refresh(obj)
    return OccupancyOut.model_validate(obj).model_dump()