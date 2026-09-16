from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db
from app.modules.complexes.models import Complex, Tower, Unit
from app.modules.complexes.schemas import (
    ComplexCreate,
    ComplexOut,
    TowerCreate,
    TowerOut,
    TowerUpdate,
    UnitCreate,
    UnitOut,
    UnitUpdate,
)
from app.modules.identity.models import User

router = APIRouter(tags=["Complexes"])


@router.get("/complexes")
async def list_complexes(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Complex).where(Complex.is_active.is_(True)))
    return [ComplexOut.model_validate(c).model_dump() for c in result.scalars().all()]


@router.post("/complexes")
async def create_complex(body: ComplexCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = Complex(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return ComplexOut.model_validate(obj).model_dump()


@router.get("/towers")
async def list_towers(complex_id: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Tower)
    if complex_id:
        query = query.where(Tower.complex_id == complex_id)
    result = await db.execute(query)
    return [TowerOut.model_validate(t).model_dump() for t in result.scalars().all()]


@router.post("/towers")
async def create_tower(body: TowerCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = Tower(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return TowerOut.model_validate(obj).model_dump()


@router.get("/towers/{tower_id}")
async def get_tower(tower_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Tower, tower_id)
    if not obj:
        raise NotFoundError("برج یافت نشد")
    return TowerOut.model_validate(obj).model_dump()


@router.patch("/towers/{tower_id}")
async def update_tower(tower_id: str, body: TowerUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Tower, tower_id)
    if not obj:
        raise NotFoundError("برج یافت نشد")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return TowerOut.model_validate(obj).model_dump()


@router.delete("/towers/{tower_id}")
async def delete_tower(tower_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Tower, tower_id)
    if not obj:
        raise NotFoundError("برج یافت نشد")
    unit_count = await db.scalar(select(func.count()).select_from(
        select(Unit.id).where(Unit.tower_id == tower_id).subquery())) or 0
    if unit_count > 0:
        raise ConflictError(f"این برج {unit_count} واحد دارد — ابتدا واحدها را حذف/منتقل کنید")
    await db.delete(obj)
    await db.commit()
    return {"success": True}


@router.get("/units")
async def list_units(tower_id: str | None = None, page: int = 1, page_size: int = 50, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Unit)
    if tower_id:
        query = query.where(Unit.tower_id == tower_id)
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    return [UnitOut.model_validate(u).model_dump() for u in result.scalars().all()]


@router.post("/units")
async def create_unit(body: UnitCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = Unit(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return UnitOut.model_validate(obj).model_dump()


@router.get("/units/{unit_id}")
async def get_unit(unit_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Unit, unit_id)
    if not obj:
        raise NotFoundError("واحد یافت نشد")
    return UnitOut.model_validate(obj).model_dump()


@router.patch("/units/{unit_id}")
async def update_unit(unit_id: str, body: UnitUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Unit, unit_id)
    if not obj:
        raise NotFoundError("واحد یافت نشد")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return UnitOut.model_validate(obj).model_dump()


@router.delete("/units/{unit_id}")
async def delete_unit(unit_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.modules.parking.models import ParkingAssignment
    from app.modules.residents.models import UnitOccupancy
    from app.modules.vehicles.models import Vehicle

    obj = await db.get(Unit, unit_id)
    if not obj:
        raise NotFoundError("واحد یافت نشد")

    occ = await db.scalar(select(func.count()).select_from(
        select(UnitOccupancy.id).where(UnitOccupancy.unit_id == unit_id).subquery())) or 0
    veh = await db.scalar(select(func.count()).select_from(
        select(Vehicle.id).where(Vehicle.unit_id == unit_id).subquery())) or 0
    asg = await db.scalar(select(func.count()).select_from(
        select(ParkingAssignment.id).where(ParkingAssignment.unit_id == unit_id).subquery())) or 0
    if occ or veh or asg:
        raise ConflictError(f"این واحد دارای ارجاع است (سکونت: {occ}، خودرو: {veh}، پارکینگ: {asg}) — ابتدا آن‌ها را حذف کنید")
    await db.delete(obj)
    await db.commit()
    return {"success": True}