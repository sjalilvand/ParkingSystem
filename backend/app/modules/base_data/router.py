from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db
from app.modules.base_data.models import PlateRegion, VehicleBrand, VehicleColor, VehicleModel, VehicleSubModel
from app.modules.complexes.models import Tower, Unit
from app.modules.identity.models import User

router = APIRouter(prefix="/base-data", tags=["BaseData"])


class BrandCreate(BaseModel):
    name_fa: str
    name_en: str | None = None
    country: str = "IR"


class ColorCreate(BaseModel):
    name_fa: str
    hex_code: str = "#9E9E9E"


class PlateRegionCreate(BaseModel):
    plate_code: str
    province: str
    city: str
    letters: str | None = None


class CsvImport(BaseModel):
    csv: str


@router.get("/brands")
async def list_brands(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(VehicleBrand).order_by(VehicleBrand.country, VehicleBrand.name_fa))
    return [{"id": b.id, "name_fa": b.name_fa, "name_en": b.name_en,
             "country": b.country, "is_active": b.is_active} for b in result.scalars().all()]


@router.post("/brands")
async def create_brand(body: BrandCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    dup = (await db.execute(select(VehicleBrand).where(VehicleBrand.name_fa == body.name_fa))).scalar_one_or_none()
    if dup:
        raise ConflictError("این برند قبلا ثبت شده است")
    obj = VehicleBrand(name_fa=body.name_fa, name_en=body.name_en, country=body.country)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "name_fa": obj.name_fa}


@router.delete("/brands/{brand_id}")
async def delete_brand(brand_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(VehicleBrand, brand_id)
    if not obj:
        raise NotFoundError("برند یافت نشد")
    await db.delete(obj)
    await db.commit()
    return {"success": True}


@router.get("/colors")
async def list_colors(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(VehicleColor).order_by(VehicleColor.name_fa))
    return [{"id": c.id, "name_fa": c.name_fa, "hex_code": c.hex_code, "is_active": c.is_active}
            for c in result.scalars().all()]


@router.post("/colors")
async def create_color(body: ColorCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    dup = (await db.execute(select(VehicleColor).where(VehicleColor.name_fa == body.name_fa))).scalar_one_or_none()
    if dup:
        raise ConflictError("این رنگ قبلا ثبت شده است")
    obj = VehicleColor(name_fa=body.name_fa, hex_code=body.hex_code)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "name_fa": obj.name_fa, "hex_code": obj.hex_code}


@router.delete("/colors/{color_id}")
async def delete_color(color_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(VehicleColor, color_id)
    if not obj:
        raise NotFoundError("رنگ یافت نشد")
    await db.delete(obj)
    await db.commit()
    return {"success": True}


# ---------------- پلاک‌های ایران (جدول پایه) ----------------

@router.get("/plate-regions")
async def list_plate_regions(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(PlateRegion).order_by(PlateRegion.plate_code, PlateRegion.city))
    return [{
        "id": r.id, "plate_code": r.plate_code, "province": r.province,
        "city": r.city, "letters": r.letters,
    } for r in result.scalars().all()]


@router.post("/plate-regions")
async def create_plate_region(body: PlateRegionCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    dup = (await db.execute(select(PlateRegion).where(
        PlateRegion.plate_code == body.plate_code,
        PlateRegion.city == body.city,
        PlateRegion.letters == body.letters,
    ))).scalar_one_or_none()
    if dup:
        raise ConflictError("این ردیف قبلا ثبت شده است")
    obj = PlateRegion(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id}


@router.post("/plate-regions/import-csv")
async def import_plate_regions_csv(body: CsvImport, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Import متن CSV — جداکننده پشتیبانی‌شده: , ; | tab — ستون‌ها: کد,استان,شهر,حروف"""
    created, skipped = 0, 0
    for raw_line in body.csv.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.replace("\t", "|").replace(";", "|").replace(",", "|").split("|")]
        parts = [p for p in parts if p not in ("",)]
        # حذف ستون id عددی در صورت وجود
        if len(parts) >= 5 and parts[0].isdigit():
            parts = parts[1:]
        if len(parts) < 3:
            skipped += 1
            continue
        code = parts[0] if not parts[0].isdigit() or len(parts) < 4 else parts[0]
        # ساختار متداول: code, province, city, letters
        if len(parts) >= 4:
            code, province, city, letters = parts[0], parts[1], parts[2], parts[3]
        else:
            code, province, city, letters = parts[0], parts[1], parts[2], ""
        if not code.isdigit() or len(code) > 2:
            skipped += 1
            continue
        dup = (await db.execute(select(PlateRegion).where(
            PlateRegion.plate_code == code,
            PlateRegion.city == city,
            PlateRegion.letters == letters,
        ))).scalar_one_or_none()
        if dup:
            skipped += 1
            continue
        db.add(PlateRegion(plate_code=code, province=province, city=city, letters=letters))
        created += 1
    await db.commit()
    return {"success": True, "created": created, "skipped": skipped}


@router.delete("/plate-regions/{region_id}")
async def delete_plate_region(region_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(PlateRegion, region_id)
    if not obj:
        raise NotFoundError("ردیف یافت نشد")
    await db.delete(obj)
    await db.commit()
    return {"success": True}

@router.get("/embed")
async def embed(callback: str = "cb", db: AsyncSession = Depends(get_db)):
    """دیتاپایه برای فرم Google Apps Script (JSONP — بدون احراز هویت، فقط خواندنی)."""
    import json as _json
    brands = (await db.execute(select(VehicleBrand).where(VehicleBrand.is_active == True))).scalars().all()  # noqa: E712
    colors = (await db.execute(select(VehicleColor).where(VehicleColor.is_active == True))).scalars().all()  # noqa: E712
    towers = (await db.execute(select(Tower))).scalars().all()
    units  = (await db.execute(select(Unit))).scalars().all()
    regions = (await db.execute(select(PlateRegion))).scalars().all()
    payload = _json.dumps({
        "brands": [b.name_fa for b in brands],
        "colors": [{"name": c.name_fa, "hex": c.hex_code} for c in colors],
        "towers": [{"name": t.name,
                    "units": [{"id": u.id, "unit_number": u.unit_number}
                              for u in units if u.tower_id == t.id]} for t in towers],
        "regions": [{"code": r.plate_code, "province": r.province, "city": r.city,
                     "letters": (r.letters or "").split()} for r in regions],
    }, ensure_ascii=False)
    cb = "".join(ch for ch in callback if ch.isalnum() or ch in "_.") or "cb"
    return Response(content=cb + "(" + payload + ");", media_type="application/javascript")


@router.get("/vehicle-catalog")
async def vehicle_catalog(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """درخت کامل: برند -> مدل -> [زیرمدل‌ها]."""
    brands = (await db.execute(select(VehicleBrand).where(
        VehicleBrand.is_active == True).order_by(VehicleBrand.name_fa))).scalars().all()  # noqa: E712
    models = (await db.execute(select(VehicleModel).where(
        VehicleModel.is_active == True))).scalars().all()  # noqa: E712
    subs = (await db.execute(select(VehicleSubModel).where(
        VehicleSubModel.is_active == True))).scalars().all()  # noqa: E712

    subs_by_model: dict = {}
    for s in subs:
        if s.name:
            subs_by_model.setdefault(s.model_id, []).append({"id": s.id, "name": s.name})  # NULLFILTER
    models_by_brand: dict = {}
    for mo in models:
        if mo.name:
            models_by_brand.setdefault(mo.brand_id, []).append(  # NULLFILTER
            {"name": mo.name, "submodels": subs_by_model.get(mo.id, [])})

    return [{"name": b.name_fa, "models": models_by_brand.get(b.id, [])} for b in brands]


@router.get("/vehicle-models")
async def vehicle_models(brand: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    b = (await db.execute(select(VehicleBrand).where(VehicleBrand.name_fa == brand))).scalar_one_or_none()
    if not b:
        return []
    rows = (await db.execute(select(VehicleModel).where(
        VehicleModel.brand_id == b.id, VehicleModel.is_active == True).order_by(VehicleModel.name))).scalars().all()  # noqa: E712
    return [m.name for m in rows]


@router.get("/vehicle-submodels")
async def vehicle_submodels(brand: str, model: str, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    b = (await db.execute(select(VehicleBrand).where(VehicleBrand.name_fa == brand))).scalar_one_or_none()
    if not b:
        return []
    mo = (await db.execute(select(VehicleModel).where(
        VehicleModel.brand_id == b.id, VehicleModel.name == model))).scalar_one_or_none()
    if not mo:
        return []
    rows = (await db.execute(select(VehicleSubModel).where(
        VehicleSubModel.model_id == mo.id, VehicleSubModel.is_active == True).order_by(VehicleSubModel.name))).scalars().all()  # noqa: E712
    return [s.name for s in rows]

# ---------------- CRUD مدل و زیرمدل ----------------

class BrandUpdate(BaseModel):
    name_fa: str


@router.patch("/brands/{brand_id}")
async def update_brand(brand_id: str, body: BrandUpdate,
                       db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    b = await db.get(VehicleBrand, brand_id)
    if not b:
        raise NotFoundError("برند یافت نشد")
    dup = (await db.execute(select(VehicleBrand).where(
        VehicleBrand.name_fa == body.name_fa, VehicleBrand.id != brand_id))).scalar_one_or_none()
    if dup:
        raise ConflictError("برند تکراری است")
    b.name_fa = body.name_fa
    await db.commit()
    return {"success": True}


class VehicleModelCreate(BaseModel):
    brand_name: str
    name: str


class NameUpdate(BaseModel):
    name: str


@router.post("/vehicle-models")
async def create_vehicle_model(body: VehicleModelCreate,
                               db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    b = (await db.execute(select(VehicleBrand).where(
        VehicleBrand.name_fa == body.brand_name))).scalar_one_or_none()
    if not b:
        raise NotFoundError("برند یافت نشد")
    dup = (await db.execute(select(VehicleModel).where(
        VehicleModel.brand_id == b.id, VehicleModel.name == body.name))).scalar_one_or_none()
    if dup:
        raise ConflictError("این مدل قبلا ثبت شده است")
    obj = VehicleModel(brand_id=b.id, name=body.name)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "name": obj.name}


@router.patch("/vehicle-models/{model_id}")
async def update_vehicle_model(model_id: str, body: NameUpdate,
                               db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    mo = await db.get(VehicleModel, model_id)
    if not mo:
        raise NotFoundError("مدل یافت نشد")
    mo.name = body.name
    await db.commit()
    return {"success": True}


@router.delete("/vehicle-models/{model_id}")
async def delete_vehicle_model(model_id: str, db: AsyncSession = Depends(get_db),
                               user: User = Depends(get_current_user)):
    subs = (await db.execute(select(VehicleSubModel).where(
        VehicleSubModel.model_id == model_id))).scalars().all()
    for s in subs:
        await db.delete(s)
    mo = await db.get(VehicleModel, model_id)
    if not mo:
        raise NotFoundError("مدل یافت نشد")
    await db.delete(mo)
    await db.commit()
    return {"success": True}


class VehicleSubCreate(BaseModel):
    model_id: str
    name: str


@router.post("/vehicle-submodels")
async def create_vehicle_sub(body: VehicleSubCreate,
                             db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    mo = await db.get(VehicleModel, body.model_id)
    if not mo:
        raise NotFoundError("مدل یافت نشد")
    dup = (await db.execute(select(VehicleSubModel).where(
        VehicleSubModel.model_id == body.model_id, VehicleSubModel.name == body.name))).scalar_one_or_none()
    if dup:
        raise ConflictError("این زیرمدل قبلا ثبت شده است")
    obj = VehicleSubModel(model_id=body.model_id, name=body.name)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "name": obj.name}


@router.patch("/vehicle-submodels/{sub_id}")
async def update_vehicle_sub(sub_id: str, body: NameUpdate,
                             db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    s = await db.get(VehicleSubModel, sub_id)
    if not s:
        raise NotFoundError("زیرمدل یافت نشد")
    s.name = body.name
    await db.commit()
    return {"success": True}


@router.delete("/vehicle-submodels/{sub_id}")
async def delete_vehicle_sub(sub_id: str, db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user)):
    s = await db.get(VehicleSubModel, sub_id)
    if not s:
        raise NotFoundError("زیرمدل یافت نشد")
    await db.delete(s)
    await db.commit()
    return {"success": True}
