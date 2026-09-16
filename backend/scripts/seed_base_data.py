import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.modules.base_data.models import VehicleBrand, VehicleColor  # noqa: E402

BRANDS = [
    ("سایپا", "Saipa", "IR"),
    ("ایران‌خودرو", "IKCO", "IR"),
    ("بهمن‌موتور", "Bahman Group", "IR"),
    ("مدن‌خودرو", "Modiran", "IR"),
    ("خراسان‌خودرو", "Khorasan", "IR"),
    ("شهاب‌خودرو", "Shahab Khodro", "IR"),
    ("مرتب", "Morattab", "IR"),
    ("کیا", "Kia", "IMPORT"),
    ("هیوندای", "Hyundai", "IMPORT"),
    ("تویوتا", "Toyota", "IMPORT"),
    ("مزدا", "Mazda", "IMPORT"),
    ("رنو", "Renault", "IMPORT"),
    ("نیسان", "Nissan", "IMPORT"),
    ("ام‌جی", "MG", "IMPORT"),
    ("جیلی", "Geely", "IMPORT"),
    ("ام‌وی‌ام", "MVM", "IMPORT"),
    ("چری", "Chery", "IMPORT"),
    ("دانگ‌فنگ", "Dongfeng", "IMPORT"),
    ("لیفان", "Lifan", "IMPORT"),
    ("جک", "JAC", "IMPORT"),
    ("لکسوس", "Lexus", "IMPORT"),
    ("مرسدس‌بنز", "Mercedes-Benz", "IMPORT"),
    ("بی‌ام‌و", "BMW", "IMPORT"),
    ("آئودی", "Audi", "IMPORT"),
    ("فولکس‌واگن", "Volkswagen", "IMPORT"),
    ("پژو", "Peugeot", "IMPORT"),
    ("سیتروئن", "Citroen", "IMPORT"),
    ("فورد", "Ford", "IMPORT"),
    ("شورلت", "Chevrolet", "IMPORT"),
]

COLORS = [
    ("سفید", "#FFFFFF"), ("مشکی", "#212121"), ("نقره‌ای", "#C0C0C0"),
    ("خاکستری", "#9E9E9E"), ("قرمز", "#E53935"), ("آبی", "#1E88E5"),
    ("سرمه‌ای", "#0D47A1"), ("سبز", "#2E7D32"), ("زرد", "#FDD835"),
    ("نارنجی", "#FB8C00"), ("قهوه‌ای", "#795548"), ("بژ", "#D7CCC8"),
    ("طلایی", "#FFD700"), ("فیروزه‌ای", "#26C6DA"), ("بنفش", "#8E24AA"),
]


async def seed_base_data():
    async with AsyncSessionLocal() as db:
        for name_fa, name_en, country in BRANDS:
            dup = (await db.execute(select(VehicleBrand).where(VehicleBrand.name_fa == name_fa))).scalar_one_or_none()
            if dup is None:
                db.add(VehicleBrand(name_fa=name_fa, name_en=name_en, country=country))
        for name_fa, hex_code in COLORS:
            dup = (await db.execute(select(VehicleColor).where(VehicleColor.name_fa == name_fa))).scalar_one_or_none()
            if dup is None:
                db.add(VehicleColor(name_fa=name_fa, hex_code=hex_code))
        await db.commit()
    print(f"OK - base data seeded: {len(BRANDS)} brands, {len(COLORS)} colors")


if __name__ == "__main__":
    asyncio.run(seed_base_data())