import asyncio
import sys

import asyncpg

URL = "postgresql://parking:parking_pass@127.0.0.1:5433/parking_db"


async def main() -> int:
    try:
        conn = await asyncpg.connect(URL, timeout=8)
    except Exception as exc:
        print("RESULT=FAIL")
        print(f"ERRTYPE={type(exc).__name__}")
        print(f"ERRMSG={str(exc)[:300]}")
        return 1
    try:
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        print("RESULT=OK")
        print(f"VERSION={str(version)[:60]}")
        return 0
    except Exception as exc:
        print("RESULT=FAIL")
        print(f"ERRTYPE={type(exc).__name__}")
        print(f"ERRMSG={str(exc)[:300]}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))