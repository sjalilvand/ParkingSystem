import asyncio
from sqlalchemy import inspect, text
from app.db.session import engine

async def main():
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
        plate_tables = [t for t in tables if "plate" in t.lower()]
        print("PLATE TABLES:", plate_tables)
        for t in plate_tables:
            try:
                n = (await conn.execute(text(f'SELECT COUNT(*) FROM "{t}"'))).scalar()
                print(f"  {t}: {n} rows")
                cols = await conn.run_sync(lambda c: [x["name"] for x in inspect(c).get_columns(t)])
                print("  columns:", cols)
                if n:
                    rows = (await conn.execute(text(f'SELECT * FROM "{t}" LIMIT 3'))).mappings().all()
                    for r in rows:
                        print("  sample:", dict(r))
            except Exception as e:
                print("  query error:", e)

try:
    asyncio.run(main())
except Exception as e:
    print("DB CONNECT FAILED:", type(e).__name__, str(e)[:300])
