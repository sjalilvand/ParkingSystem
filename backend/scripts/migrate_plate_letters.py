"""D8 (F18) — Migration نگاشت یکتای حروف پلاک.

کاربرد (از پوشه backend، با DATABASE_URL صحیح):
    python scripts/migrate_plate_letters.py                 # حالت پیش‌نمایش (dry-run)
    python scripts/migrate_plate_letters.py --apply         # اجرای واقعی

منطق:
  1. vehicles: بازنرمال‌سازی از plate_raw (منبع حقیقت فارسی) با جدول نگاشت مقصد
     + بروزرسانی plate_letter.
  2. سایر جداول فقط plate_normalized دارند (permits/parking_sessions/
     access_events/plate_recognition_events/payments): نگاشت از طریق
     تطبیق با mapping ساخته‌شده از vehicles انجام می‌شود.
  3. پلاک‌هایی که معادل یکتا ندارند (فقط در MANY_TO_ONE→UNIQUE ممکن است)
     دست‌نخورده می‌مانند و در گزارش پایان نمایش داده می‌شوند.

هشدار: قبل از اجرا پشتیبان‌گیری کامل DB الزامی است (scripts/backup-db.ps1).
"""
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.shared.plate import (  # noqa: E402
    LETTER_MAP,
    UNIQUE_LETTER_MAP,
    get_letter_map,
    normalize_plate,
    remap_normalized_plate,
)


def build_old_to_new_map(target_mode: str) -> tuple[dict, list]:
    """ساخت نگاشت normalized-قدیم → normalized-جدید از داده واقعی vehicles انجام نمی‌شود
    اینجا؛ تابع فقط نقشه حروف را می‌سازد و در اجرا از plate_raw استفاده می‌شود.
    خروجی: (letter_map_target, unresolvable_hint)"""
    return get_letter_map(target_mode), []


async def migrate(target_mode: str = "UNIQUE", apply: bool = False) -> None:
    from app.modules.access_control.models import AccessEvent, ParkingSession, PlateRecognitionEvent
    from app.modules.finance.models import Payment
    from app.modules.vehicles.models import AccessPermit, Vehicle

    target_map = get_letter_map(target_mode)
    print(f"[D8] target mapping mode = {target_mode} ({len(target_map)} letters)")

    async with AsyncSessionLocal() as db:
        # --- 1) vehicles از plate_raw ---
        vehicles = (await db.execute(select(Vehicle))).scalars().all()
        vehicle_map: dict[str, str] = {}  # old_normalized -> new_normalized
        v_changed = v_unresolved = 0
        for v in vehicles:
            old_norm = v.plate_normalized
            new_norm = normalize_plate(v.plate_raw, letter_mapping=target_mode)
            if not new_norm:
                v_unresolved += 1
                continue
            if new_norm != old_norm:
                v_changed += 1
            if old_norm:
                vehicle_map[old_norm] = new_norm
        print(f"[D8] vehicles: {len(vehicles)} rows, changed={v_changed}, unresolved_raw={v_unresolved}")

        # --- 2) جداول فقط-normalized از طریق vehicle_map ---
        def map_norm(old: str | None) -> str | None:
            if not old:
                return None
            if old in vehicle_map:
                return vehicle_map[old]
            # پلاک ناشناس (بدون خودرو): تلاش برای تبدیل برگشت‌پذیر — فقط در حالت UNIQUE مبدا
            return remap_normalized_plate(old, LETTER_MAP, target_map) or None

        stats = {}
        if apply:
            for v in vehicles:
                new_norm = normalize_plate(v.plate_raw, letter_mapping=target_mode)
                if new_norm:
                    v.plate_normalized = new_norm
                    # استخراج کد حرف جدید برای ستون plate_letter
                    m = remap_normalized_plate(new_norm, target_map, target_map)
                    v.plate_letter = new_norm[2:4] if new_norm[2:3].isalpha() else new_norm[2:3]
            await db.flush()

        permits = (await db.execute(select(AccessPermit))).scalars().all()
        p_changed = 0
        for p in permits:
            new_norm = map_norm(p.plate_normalized)
            if new_norm and new_norm != p.plate_normalized:
                p_changed += 1
                if apply:
                    p.plate_normalized = new_norm
        stats["access_permits"] = p_changed

        sessions = (await db.execute(select(ParkingSession))).scalars().all()
        s_changed = 0
        for s in sessions:
            new_norm = map_norm(s.plate_normalized)
            if new_norm and new_norm != s.plate_normalized:
                s_changed += 1
                if apply:
                    s.plate_normalized = new_norm
        stats["parking_sessions"] = s_changed

        events = (await db.execute(select(AccessEvent))).scalars().all()
        e_changed = 0
        for ev in events:
            new_norm = map_norm(ev.plate_normalized)
            if new_norm and new_norm != ev.plate_normalized:
                e_changed += 1
                if apply:
                    ev.plate_normalized = new_norm
        stats["access_events"] = e_changed

        pre_events = (await db.execute(select(PlateRecognitionEvent))).scalars().all()
        pr_changed = 0
        for pe in pre_events:
            # plate_recognition_events دارای plate_raw است — بازنرمال‌سازی مستقیم
            new_norm = normalize_plate(pe.plate_raw, letter_mapping=target_mode)
            if new_norm and new_norm != pe.plate_normalized:
                pr_changed += 1
                if apply:
                    pe.plate_normalized = new_norm
        stats["plate_recognition_events"] = pr_changed

        payments = (await db.execute(select(Payment))).scalars().all()
        pay_changed = 0
        for pay in payments:
            new_norm = map_norm(pay.plate_normalized)
            if new_norm and new_norm != pay.plate_normalized:
                pay_changed += 1
                if apply:
                    pay.plate_normalized = new_norm
        stats["payments"] = pay_changed

        print("[D8] dry-run stats:" if not apply else "[D8] applied stats:")
        for table, changed in stats.items():
            print(f"    {table}: changed={changed}")

        unmapped = [old for old in vehicle_map.values() if old is None]
        if apply:
            await db.commit()
            print("[D8] COMMIT OK — migration اعمال شد.")
        else:
            await db.rollback()
            print("[D8] DRY-RUN — هیچ تغییری ذخیره نشد. برای اعمال: --apply")
        if unmapped:
            print(f"[D8] warning: {len(unmapped)} plates بدون معادل یکتا (دست‌نخورده ماندند)")


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    mode = "UNIQUE"
    if "--mode" in args:
        mode = args[args.index("--mode") + 1].upper()
    if mode not in ("MANY_TO_ONE", "UNIQUE"):
        print("mode باید MANY_TO_ONE یا UNIQUE باشد")
        sys.exit(2)
    asyncio.run(migrate(mode, apply))


if __name__ == "__main__":
    main()
