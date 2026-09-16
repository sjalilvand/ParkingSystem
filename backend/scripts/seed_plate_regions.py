import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.modules.base_data.models import PlateRegion  # noqa: E402

CSV_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "IranPlates_Full.csv",
    Path(__file__).resolve().parents[1] / "IranPlates_Full.csv",
    Path(__file__).resolve().parents[1] / "app" / "shared" / "data" / "iran_plates_full.csv",
]


def find_csv() -> Path:
    for p in CSV_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("IranPlates_Full.csv یافت نشد — فایل را در ریشه پروژه قرار دهید")


def parse_rows(csv_path: Path):
    """فرمت‌های پشتیبانی‌شده:
    [کد, استان, شهرستان, حروف]
    [id, کد, استان, شهرستان, حروف]
    [serial, id, کد, استان, شهرستان, حروف]   <- IranPlates_Full.csv فعلی
    """
    text = csv_path.read_text(encoding="utf-8-sig")
    rows, seen, skipped = [], set(), 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        sep = "|" if "|" in line else (";" if ";" in line else ",")
        parts = [p.strip() for p in line.split(sep)]
        parts = [p for p in parts if p]
        if len(parts) < 4:
            skipped += 1
            continue
        # حذف ستون‌های عددی اضافه (serial/id) از ابتدا — تا رسیدن به ساختار ۴ ستونی
        while len(parts) > 4 and parts[0].isdigit():
            parts = parts[1:]
        if len(parts) < 4:
            skipped += 1
            continue
        code, province, city, letters = parts[0], parts[1], parts[2], parts[3]
        if not code.isdigit() or len(code) > 2:
            skipped += 1
            continue  # هدر یا ردیف نامعتبر
        if province in ("استان", "ایدی") or "کد پلاک" in province:
            skipped += 1
            continue  # هدر
        if "تخصیص" in province:
            continue  # کد تخصیص‌نیافته
        letters = " ".join(letters.split())  # فاصله‌های تکراری
        key = (code, city, letters)
        if key in seen:
            continue
        seen.add(key)
        rows.append((code, province, city, letters))
    return rows, skipped


async def reseed():
    csv_path = find_csv()
    print(f">>> CSV: {csv_path}")
    rows, skipped = parse_rows(csv_path)
    codes = sorted({r[0] for r in rows}, key=int)
    print(f">>> valid rows: {len(rows)} | unique plate codes: {len(codes)} | skipped: {skipped}")
    if len(rows) < 300:
        print("!! تعداد ردیف‌ها کمتر از انتظار است — ساختار CSV را بررسی کنید")
        return

    async with AsyncSessionLocal() as db:
        old = await db.scalar(select(func.count()).select_from(PlateRegion))
        await db.execute(delete(PlateRegion))
        for code, province, city, letters in rows:
            db.add(PlateRegion(plate_code=code, province=province, city=city, letters=letters))
        await db.commit()
        new = await db.scalar(select(func.count()).select_from(PlateRegion))
        print(f">>> reseed done: old={old} -> new={new}")

    # ---------- verification ----------
    def lookup(code: str, letter: str):
        for c, p, city, ls in rows:
            if c == code and letter in ls.split(" "):
                return p, city
        return None, None

    tests = [("67", "ب", "اصفهان"), ("21", "و", "کرج"), ("30", "د", "کرج"),
             ("28", "ب", "نهاوند"), ("12", "ب", "مشهد"), ("35", "ز", "میانه")]
    ok = 0
    for code, letter, expected in tests:
        p, city = lookup(code, letter)
        mark = "OK  " if p else "FAIL"
        if p:
            ok += 1
        print(f"   [{mark}] {code}+{letter} -> {p} / {city}  (expected: {expected})")
    print(f">>> verification: {ok}/{len(tests)} passed")
    if ok < len(tests):
        print("!! بعضی ترکیب‌ها پیدا نشدند — خروجی را برای بررسی بفرستید")


if __name__ == "__main__":
    asyncio.run(reseed())