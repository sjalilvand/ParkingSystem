from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db
from app.modules.base_data.models import PlateRegion
from app.modules.complexes.models import Tower, Unit
from app.modules.identity.models import User
from app.modules.residents.models import Person
from app.modules.vehicles.models import Vehicle, VehicleRestriction
from app.modules.vehicles.schemas import RestrictionCreate, VehicleOut
from app.modules.vehicles.service import VehicleService
from app.shared.plate import normalize_plate

router = APIRouter(tags=["Vehicles"])


class VehicleCreate(BaseModel):
    owner_person_id: str | None = None
    unit_id: str | None = None
    plate_raw: str = Field(min_length=2, max_length=64)
    plate_letter: str | None = None
    plate_province_code: str | None = None
    plate_type: str = "PERSONAL"
    vehicle_type: str = "CAR"
    brand: str | None = None
    model: str | None = None
    color: str | None = None
    year: int | None = None
    notes: str | None = None


class VehicleUpdate(BaseModel):
    owner_person_id: str | None = None
    unit_id: str | None = None
    plate_raw: str | None = Field(default=None, min_length=2, max_length=64)
    plate_letter: str | None = None
    plate_province_code: str | None = None
    vehicle_type: str | None = None
    brand: str | None = None
    model: str | None = None
    color: str | None = None
    year: int | None = None
    is_active: bool | None = None
    notes: str | None = None


async def resolve_region(db: AsyncSession, letter: str | None, code: str | None):
    """جدول پایه پلاک‌ها: کد استان + حرف => (استان، شهر)."""
    if not letter or not code:
        return None, None
    rows = (await db.execute(
        select(PlateRegion).where(PlateRegion.plate_code == code)
    )).scalars().all()
    letter = letter.strip()
    for r in rows:
        if letter in (r.letters or "").split():
            return r.province, r.city
    return None, None


@router.get("/vehicles")
async def list_vehicles(search: str | None = None, page: int = 1, page_size: int = 50,
                        db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Vehicle)
    if search:
        like = f"%{search}%"
        query = query.where(or_(
            Vehicle.plate_normalized.ilike(like), Vehicle.brand.ilike(like),
            Vehicle.color.ilike(like), Vehicle.model.ilike(like),
            Vehicle.plate_province.ilike(like), Vehicle.plate_city.ilike(like)))

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await db.execute(
        query.order_by(Vehicle.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    items = []
    for v in rows:
        owner_name = None
        if v.owner_person_id:
            p = await db.get(Person, v.owner_person_id)
            if p:
                owner_name = f"{p.first_name} {p.last_name}".strip()
        unit_number = tower_name = None
        if v.unit_id:
            u = await db.get(Unit, v.unit_id)
            if u:
                unit_number = u.unit_number
                t = await db.get(Tower, u.tower_id)
                tower_name = t.name if t else None
        items.append({
            **VehicleOut.model_validate(v).model_dump(),
            "owner_name": owner_name, "unit_number": unit_number, "tower_name": tower_name,
        })
    total_items = total or 0
    return {"items": items, "page": page, "page_size": page_size,
            "total_items": total_items, "total_pages": (total_items + page_size - 1) // page_size}


@router.post("/vehicles")
async def create_vehicle(body: VehicleCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    data = body.model_dump()
    raw = data.pop("plate_raw")
    letter = data.pop("plate_letter", None)
    code = data.pop("plate_province_code", None)
    normalized = normalize_plate(raw) or raw
    existing = await VehicleService.get_by_plate(db, raw)
    if existing:
        raise ConflictError("خودرویی با این پلاک قبلا ثبت شده است",
                           details={"plate": normalized, "vehicle_id": existing.id})
    province, city = await resolve_region(db, letter, code)
    obj = Vehicle(plate_raw=raw, plate_normalized=normalized,
                  plate_letter=letter, plate_province_code=code,
                  plate_province=province, plate_city=city, **data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return VehicleOut.model_validate(obj).model_dump()


@router.get("/vehicles/by-plate/{plate}")
async def get_by_plate(plate: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    vehicle = await VehicleService.get_by_plate(db, plate)
    if not vehicle:
        raise NotFoundError("خودرویی با این پلاک یافت نشد")
    return VehicleOut.model_validate(vehicle).model_dump()


@router.get("/vehicles/{vehicle_id}")
async def get_vehicle(vehicle_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Vehicle, vehicle_id)
    if not obj:
        raise NotFoundError("خودرو یافت نشد")
    return VehicleOut.model_validate(obj).model_dump()


@router.patch("/vehicles/{vehicle_id}")
async def update_vehicle(vehicle_id: str, body: VehicleUpdate,
                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Vehicle, vehicle_id)
    if not obj:
        raise NotFoundError("خودرو یافت نشد")
    data = body.model_dump(exclude_unset=True)
    new_raw = data.pop("plate_raw", None)
    letter = data.pop("plate_letter", None)
    code = data.pop("plate_province_code", None)
    if new_raw:
        normalized = normalize_plate(new_raw) or new_raw
        if normalized != obj.plate_normalized:
            dup = (await db.execute(select(Vehicle).where(Vehicle.plate_normalized == normalized))).scalars().first()
            if dup and dup.id != obj.id:
                raise ConflictError("پلاک تکراری است")
        obj.plate_raw = new_raw
        obj.plate_normalized = normalized
    if letter and code:
        obj.plate_letter = letter
        obj.plate_province_code = code
        province, city = await resolve_region(db, letter, code)
        obj.plate_province = province
        obj.plate_city = city
    for k, v in data.items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return VehicleOut.model_validate(obj).model_dump()


@router.post("/vehicles/{vehicle_id}/activate")
async def activate_vehicle(vehicle_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Vehicle, vehicle_id)
    if not obj:
        raise NotFoundError("خودرو یافت نشد")
    obj.is_active = True
    await db.commit()
    return {"success": True}


@router.post("/vehicles/{vehicle_id}/deactivate")
async def deactivate_vehicle(vehicle_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Vehicle, vehicle_id)
    if not obj:
        raise NotFoundError("خودرو یافت نشد")
    obj.is_active = False
    await db.commit()
    return {"success": True}


@router.get("/units/{unit_id}/vehicles")
async def unit_vehicles(unit_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Vehicle).where(Vehicle.unit_id == unit_id))
    return [VehicleOut.model_validate(v).model_dump() for v in result.scalars().all()]


@router.get("/restrictions")
async def list_restrictions(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(VehicleRestriction).where(VehicleRestriction.status == "ACTIVE").limit(200))
    return [{"id": r.id, "plate_normalized": r.plate_normalized, "type": r.restriction_type,
             "reason": r.reason, "status": r.status} for r in result.scalars().all()]


@router.post("/restrictions")
async def create_restriction(body: RestrictionCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    normalized = normalize_plate(body.plate_raw) or body.plate_raw
    vehicle = await VehicleService.get_by_plate(db, body.plate_raw)
    obj = VehicleRestriction(vehicle_id=vehicle.id if vehicle else None, plate_normalized=normalized,
                             restriction_type=body.restriction_type, reason=body.reason,
                             created_by=user.id if user else None)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "plate_normalized": obj.plate_normalized, "status": obj.status}


@router.post("/restrictions/{restriction_id}/resolve")
async def resolve_restriction(restriction_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from datetime import datetime, timezone
    obj = await db.get(VehicleRestriction, restriction_id)
    if not obj:
        raise NotFoundError("محدودیت یافت نشد")
    obj.status = "RESOLVED"
    obj.resolved_by = user.id if user else None
    obj.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"success": True}