"""Seed کامل شبیه‌سازی: ۳ برج × ۱۶۵ واحد، ساکنین، خودروها، جایگاه‌های پارکینگ. idempotent."""
import asyncio
from pathlib import Path
import random
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.modules.base_data.models import PlateRegion
from app.modules.complexes.models import Complex, Tower, Unit
from app.modules.parking.cad_models import CadParkingSpot
from app.modules.residents.models import Person
from app.modules.vehicles.models import Vehicle

FIRST = ["علی","محمد","رضا","حسین","مهدی","امیر","نیما","سعید","حامد","کریم",
         "سارا","مریم","زهرا","فاطمه","نرگس","الناز","شیما","پریسا","الهام","مینا"]
LAST  = ["محمدی","احمدی","رضایی","حسینی","کریمی","موسوی","صادقی","جعفری","نوری","قاسمی",
         "زمانی","مرادی","شریفی","اکبری","سلطانی","کرمانی","تهرانی","اصفهانی","شیرازی","تبریزی"]
BRANDS = ["پژو","سایپا","ایران‌خودرو","کیا","هیوندای","تویوتا","ام‌وی‌ام","چری","بهدرو","مدن"]
MODELS = ["206","207i","پراید","سمند LX","دنا پلاس","سراتو","النترا","کمری","تیگو 7","ری را"]
COLORS = ["سفید","نقره‌ای","مشکی","خاکستری","آبی","قرمز","طوسی"]
LETTERS = ["ب","ج","د","س","ص","ط","ق","ل","م","ن","و","هـ","ی"]
LETTER_MAP = {"ب":"B","ج":"J","د":"D","س":"S","ص":"S","ط":"T","ق":"G","ل":"L","م":"M","ن":"N","و":"V","هـ":"H","ی":"Y"}
PROV_CODES = ["11","12","13","14","15","16","17","18","19","21","22","23","24","26","27","28","29","30",
              "32","36","38","41","43","46","47","51","53","56","57","58","59","61","63","64","65","67",
              "68","71","72","73","74","75","76","77","78","79","81","82","83","84","85","87","91","93","94","95","97","98"]

random.seed(2026)


def make_plate():
    code = random.choice(PROV_CODES)
    letter = random.choice(LETTERS)
    three = str(random.randint(100, 999))
    two = str(random.randint(10, 99))
    raw = f"{two} {letter} {three} ایران {code}"
    norm = f"{two}{LETTER_MAP[letter]}{three}IR{code}"
    return raw, norm, letter, code


async def main():
    async with AsyncSessionLocal() as db:
        # ---- مجتمع ----
        cx = (await db.execute(select(Complex))).scalars().first()
        if cx is None:
            cx = Complex(code="CMP-1", name="مجتمع مسکونی نمونه")
            db.add(cx); await db.flush()
            print("[seed] complex created")

        # ---- برج‌ها و واحدها ----
        towers = {t.name: t for t in (await db.execute(select(Tower))).scalars().all()}
        for tname in ["برج A", "برج B", "برج C"]:
            if tname not in towers:
                t = Tower(complex_id=cx.id, code=tname[-1], name=tname, floor_count=15)
                db.add(t); await db.flush()
                towers[tname] = t
                print(f"[seed] tower created: {tname}")

        unit_counts = {}
        for tname, t in towers.items():
            if tname not in ["برج A", "برج B", "برج C"]:
                continue
            n = (await db.execute(select(func.count()).select_from(Unit).where(Unit.tower_id == t.id))).scalar()
            unit_counts[tname] = n
            if n < 165:
                existing = {u.unit_number for u in (await db.execute(
                    select(Unit).where(Unit.tower_id == t.id))).scalars().all()}
                for i in range(1, 166):
                    un = str(i)
                    if un not in existing:
                        db.add(Unit(tower_id=t.id, unit_number=un, floor_number=(i - 1) // 4 + 1))
                await db.flush()
                print(f"[seed] units ensured for {tname} (had {n})")

        # ---- اگر از قبل ۴۰۰+ خودرو هست، skip ----
        vcount = (await db.execute(select(func.count()).select_from(Vehicle))).scalar()
        if vcount >= 400:
            print(f"[seed] vehicles already {vcount} - skip persons/vehicles")
            await db.commit()
        else:
            regions = (await db.execute(select(PlateRegion))).scalars().all()
            reg_by_code = {}
            for r in regions:
                reg_by_code.setdefault(r.plate_code, r)

            created_v = 0
            for tname in ["برج A", "برج B", "برج C"]:
                t = towers[tname]
                units = (await db.execute(
                    select(Unit).where(Unit.tower_id == t.id).order_by(Unit.unit_number))).scalars().all()
                for u in units:
                    # ساکن
                    first, last = random.choice(FIRST), random.choice(LAST)
                    nc = str(random.randint(1000000000, 9999999999))
                    db.add(Person(national_code=nc, first_name=first, last_name=last,
                                  mobile="09" + str(random.randint(100000000, 999999999)),
                                  person_type=random.choice(["OWNER", "OWNER", "TENANT"])))
                    await db.flush()
                    # خودرو
                    while True:
                        raw, norm, letter, code = make_plate()
                        dup = (await db.execute(select(Vehicle).where(
                            Vehicle.plate_normalized == norm))).scalar_one_or_none()
                        if dup is None:
                            break
                    reg = reg_by_code.get(code)
                    db.add(Vehicle(
                        owner_person_id=None,  # بعد از flush پر می‌شود
                        unit_id=u.id,
                        plate_raw=raw, plate_normalized=norm,
                        plate_letter=letter, plate_province_code=code,
                        plate_province=(reg.province if reg else "تهران"),
                        plate_city=(reg.city if reg else "تهران"),
                        brand=random.choice(BRANDS), model=random.choice(MODELS),
                        color=random.choice(COLORS), year=random.randint(1395, 1404),
                        is_active=(random.random() > 0.03)))
                    created_v += 1
                print(f"[seed] vehicles for {tname}: cumulative {created_v}")
            await db.commit()

            # اتصال owner_person_id آخرین شخص هر واحد (ساده: آخرین person inserted per unit)
            # برای سادگی: مالک = شخصی که آخرین بار برای همین unit ساخته شد
            persons = (await db.execute(select(Person).order_by(Person.created_at.desc()).limit(created_v))).scalars().all()
            vehicles = (await db.execute(select(Vehicle).where(Vehicle.owner_person_id.is_(None)))).scalars().all()
            for v, p in zip(vehicles, persons):
                v.owner_person_id = p.id
            await db.commit()
            print(f"[seed] total vehicles now: {created_v}, owners linked: {min(len(persons), len(vehicles))}")

        # ---- جایگاه‌های پارکینگ (طبقات منفی + محوطه) ----
        scount = (await db.execute(select(func.count()).select_from(CadParkingSpot))).scalar()
        if scount < 400:
            for tname in ["برج A", "برج B", "برج C"]:
                tag = tname[-1]
                for level, cap in (("P1", 80), ("P2", 80)):
                    for i in range(1, cap + 1):
                        db.add(CadParkingSpot(
                            parking_code=f"{tag}-{level}-{i:03d}",
                            display_name=f"{tname} — طبقه {level} — جایگاه {i:03d}",
                            source_drawing="SIM", status="free", parking_type="RESIDENT"))
            for i in range(1, 201):
                db.add(CadParkingSpot(
                    parking_code=f"C-YARD-{i:03d}",
                    display_name=f"محوطه — جایگاه {i:03d}",
                    source_drawing="SIM", status="free", parking_type="RESIDENT"))
            await db.commit()
            print(f"[seed] parking spots created (had {scount})")
        else:
            print(f"[seed] parking spots already {scount}")

    print("[seed] SEED FULL OK")


if __name__ == "__main__":
    asyncio.run(main())