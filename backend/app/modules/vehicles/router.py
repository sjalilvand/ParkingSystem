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

_CODE_DIGITS = str.maketrans("\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669", "01234567890123456789")


def _norm_code(c):
    return c.translate(_CODE_DIGITS).strip() if c else None


def _norm_letter(s):
    if not s:
        return s
    s = s.replace("\u0640", "").replace("\u0643", "\u06a9").replace("\u064a", "\u06cc").replace("\u0649", "\u06cc")
    return s.strip()



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
    code = _norm_code(code)
    rows = (await db.execute(
        select(PlateRegion).where(PlateRegion.plate_code == code)
    )).scalars().all()
    def _norm_letter(s: str) -> str:
        return s.replace("\u0640", "").replace("ك", "ک").replace("ي", "ی").replace("ى", "ی").strip()

    letter_n = _norm_letter(letter)
    for r in rows:
        if letter_n in {_norm_letter(tok) for tok in (r.letters or "").split()}:
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
    letter = _norm_letter(data.pop("plate_letter", None) or "") or None
    code = _norm_code(data.pop("plate_province_code", None))
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
    letter = _norm_letter(data.pop("plate_letter", None) or "") or None
    code = _norm_code(data.pop("plate_province_code", None))
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


class PlateLookupBody(BaseModel):
    plate_raw: str = Field(min_length=2, max_length=64)
    code: str | None = None
    letter: str | None = None


@router.post("/vehicles/plate-lookup")
async def plate_lookup(body: PlateLookupBody, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """تشخیص ساکن/غریبه برای پنل گیت.
    RESIDENT: خودرو ثبت‌شده است -> مشخصات مالک/واحد/برج.
    GUEST: ناشناس -> استان/شهرستان از (کد استان، حرف) یا پارس خودکار raw.
    """
    raw = body.plate_raw
    normalized = normalize_plate(raw) or raw
    vehicle = await VehicleService.get_by_plate(db, raw)
    if vehicle:
        owner_name = None
        if vehicle.owner_person_id:
            p = await db.get(Person, vehicle.owner_person_id)
            if p:
                owner_name = f"{p.first_name} {p.last_name}".strip() or None
        unit_number = tower_name = None
        if vehicle.unit_id:
            u = await db.get(Unit, vehicle.unit_id)
            if u:
                unit_number = u.unit_number
                t = await db.get(Tower, u.tower_id)
                tower_name = t.name if t else None
        return {"kind": "RESIDENT", "plate_normalized": normalized,
                "owner_name": owner_name, "unit_number": unit_number, "tower_name": tower_name,
                "plate_province": vehicle.plate_province, "plate_city": vehicle.plate_city,
                "vehicle": {"id": vehicle.id, "brand": vehicle.brand, "model": vehicle.model,
                            "color": vehicle.color, "plate_raw": vehicle.plate_raw,
                            "is_active": vehicle.is_active}}

    code = _norm_code(body.code)
    if not code:
        import re as _re_ir
        _m = _re_ir.search(r"IR(\d{2})$", normalized or "")
        if _m:
            code = _m.group(1)
    letter = _norm_letter(body.letter or "") or None
    if not code or not letter:
        import re as _re
        for tok in _re.split(r"[\s\-_/,().]+", raw.translate(_CODE_DIGITS)):
            tok = tok.strip().strip('"')
            if not tok:
                continue
            if code is None and tok.isdigit() and len(tok) == 2:
                code = tok
            elif letter is None and len(tok) == 1:
                letter = tok
    province = city = None
    if code and letter:
        rows = (await db.execute(select(PlateRegion).where(PlateRegion.plate_code == code))).scalars().all()
        for r in rows:
            if letter in {_norm_letter(tok) for tok in (r.letters or "").split()}:
                province, city = r.province, r.city
                break
        if province is None and rows:
            province = rows[0].province
    return {"kind": "GUEST", "plate_normalized": normalized,
            "province": province, "city": city}
