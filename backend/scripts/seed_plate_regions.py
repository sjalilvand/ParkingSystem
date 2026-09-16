import asyncio, csv, io, re, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

CSV_CANDIDATES = [
    BACKEND_DIR.parent / "IranPlates_Full.csv",
    BACKEND_DIR / "IranPlates_Full.csv",
    BACKEND_DIR / "app" / "shared" / "data" / "iran_plates_full.csv",
]

INVISIBLE = re.compile("[\u0000\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_DIG = str.maketrans("\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669", "01234567890123456789")
PROVINCE_HEADER = ("\u0627\u0633\u062a\u0627\u0646", "\u0622\u06cc\u062f\u06cc")
KEY_CODE = "\u06a9\u062f"
KEY_UNASSIGNED = "\u062a\u062e\u0635\u06cc\u0635"


def clean(s):
    return INVISIBLE.sub("", s).strip().strip('"').strip()


def norm_letter(s):
    s = clean(s).replace("\u0640", "").replace("\u0643", "\u06a9").replace("\u064a", "\u06cc").replace("\u0649", "\u06cc")
    return " ".join(re.split(r"[\s/\u060c,;|]+", s)).strip()


def split_best(line):
    best = []
    for sep in ("\t", "|", ";", ","):
        parts = [clean(p) for p in line.split(sep)]
        parts = [p for p in parts if p]
        if len(parts) > len(best):
            best = parts
    return best


def _finalize(parts_iter):
    rows, seen, skipped, sample = [], set(), 0, None
    for raw in parts_iter:
        parts = [p for p in (clean(x) for x in raw) if p]
        if len(parts) < 4:
            skipped += 1
            continue
        while len(parts) > 4 and parts[0].translate(_DIG).isdigit():
            parts.pop(0)
        if len(parts) > 4:
            code, province, city, letters = parts[0], parts[1], parts[2], " ".join(parts[3:])
        elif len(parts) == 4:
            code, province, city, letters = parts
        else:
            skipped += 1
            continue
        code = code.translate(_DIG)
        if not code.isdigit() or len(code) > 2:
            skipped += 1
            continue
        if province in PROVINCE_HEADER or KEY_CODE in province:
            skipped += 1
            continue
        if KEY_UNASSIGNED in province:
            continue
        letters = norm_letter(letters)
        if sample is None:
            sample = (code, province, city, letters)
        key = (code, city, letters)
        if key in seen:
            continue
        seen.add(key)
        rows.append((code, province, city, letters))
    return rows, skipped, sample


def _parse_csv(text):
    return _finalize(csv.reader(io.StringIO(text)))


def _parse_manual(text):
    def gen():
        for line in text.splitlines():
            line = line.strip()
            if line:
                yield split_best(line)
    return _finalize(gen())


def parse_text(text):
    return max((_parse_csv(text), _parse_manual(text)), key=lambda r: len(r[0]))


def read_auto(path):
    raw = path.read_bytes()
    results = []
    for enc in ("utf-8-sig", "utf-16", "cp1256"):
        try:
            t = raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
        rows, skipped, sample = parse_text(t)
        results.append((enc, rows, skipped, sample))
        if len(rows) > 300:
            break
    results.sort(key=lambda r: -len(r[1]))
    return results[0] if results else (None, [], 0, None)


async def main():
    from scripts._dbpick import pick_database, activate
    url, _t = await pick_database()
    activate(url)
    print(f">>> USING: {url}")

    from sqlalchemy import delete, func, select, inspect as sqlinspect
    from app.db.session import AsyncSessionLocal, engine
    from app.modules.base_data.models import PlateRegion

    async with engine.begin() as conn:
        def _ensure(sc):
            insp = sqlinspect(sc)
            if not insp.has_table("plate_regions"):
                PlateRegion.__table__.create(sc)
                print(">>> table plate_regions CREATED")
            if insp.has_table("vehicles"):
                cols = {x["name"] for x in insp.get_columns("vehicles")}
                for name, ddl in (("plate_letter", "VARCHAR(4)"), ("plate_province_code", "VARCHAR(4)"),
                                  ("plate_province", "VARCHAR(64)"), ("plate_city", "VARCHAR(64)")):
                    if name not in cols:
                        sc.exec_driver_sql(f"ALTER TABLE vehicles ADD COLUMN {name} {ddl}")
                        print(f">>> column vehicles.{name} ADDED")
        await conn.run_sync(_ensure)

    csv_path = next((p for p in CSV_CANDIDATES if p.exists()), None)
    if not csv_path:
        print("!! CSV not found")
        return
    enc_used, rows, skipped, sample = read_auto(csv_path)
    print(f">>> CSV: {csv_path}")
    print(f">>> encoding: {enc_used}")
    print(f">>> valid rows: {len(rows)} | skipped: {skipped}")
    if sample:
        print(f">>> sample: code={sample[0]!r} province={sample[1]!r} city={sample[2]!r} letters={sample[3]!r}")
    if len(rows) < 300:
        print("!! parse failed - send this output")
        return
    codes = sorted({r[0] for r in rows}, key=int)
    print(f">>> unique plate codes: {len(codes)} ({codes[0]}..{codes[-1]})")

    async with AsyncSessionLocal() as db:
        old = await db.scalar(select(func.count()).select_from(PlateRegion))
        await db.execute(delete(PlateRegion))
        db.add_all([PlateRegion(plate_code=c, province=p, city=ci, letters=ls) for c, p, ci, ls in rows])
        await db.commit()
        new = await db.scalar(select(func.count()).select_from(PlateRegion))
        print(f">>> reseed: old={old} -> new={new}")

    def lookup(code, letter):
        for c, p, ci, ls in rows:
            if c == code and norm_letter(letter) in set(ls.split()):
                return p, ci
        return None, None

    B, V, D, Z, HE = "\u0628", "\u0648", "\u062f", "\u0632", "\u0647\u0640"
    tests = [("67", B), ("21", V), ("30", D), ("28", B), ("28", D), ("12", B), ("35", Z), ("24", HE)]
    ok = 0
    for code, letter in tests:
        p, ci = lookup(code, letter)
        ok += 1 if p else 0
        print(f"   [{'OK' if p else 'FAIL'}] {code}+{letter} -> {p} / {ci}")
    print(f">>> verification: {ok}/{len(tests)} passed")


if __name__ == "__main__":
    asyncio.run(main())