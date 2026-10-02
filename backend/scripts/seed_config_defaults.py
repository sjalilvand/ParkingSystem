"""Seed پیش‌فرض‌های پیکربندی — idempotent، منبع واحد.
هسته sync (seed_sync) برای: migration alembic (بدون loop) و پوشش async برای اجرای دستی/تست.
اجرای دستی: python -m scripts.seed_config_defaults"""
import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

GROUPS = [
    ("11111111-1111-4111-8111-111111111101", "PRIMARY_COVERED", "خودروی اصلی دارای حق پارکینگ مسقف", "PRIMARY_WITH_COVERED"),
    ("11111111-1111-4111-8111-111111111102", "SECONDARY_COVERED", "خودروی جایگزین دارای حق پارکینگ مسقف", "SECONDARY_WITH_COVERED"),
    ("11111111-1111-4111-8111-111111111103", "RESIDENT_YARD", "خودروی ساکن متقاضی محوطه", "RESIDENT_YARD"),
    ("11111111-1111-4111-8111-111111111104", "NONRESIDENT_YARD", "خودروی غیرساکن متقاضی محوطه", "NONRESIDENT_YARD"),
    ("11111111-1111-4111-8111-111111111105", "SPECIAL_PERMIT", "خودروی دارای مجوز ویژه", "SPECIAL_PERMIT"),
]

BOXES = [
    ("22222222-2222-4222-8222-222222222201", "IN",
     [{"key": "yard_request", "label": "درخواست پارک در محوطه", "visible": True},
      {"key": "own_parking", "label": "پارکینگ خودم", "visible": True},
      {"key": "help", "label": "کمک نگهبان", "visible": True}],
     {"welcome": "خوش آمدید — پلاک خود را وارد یا منتظر بمانید", "error": "خطا — به نگهبان مراجعه کنید"},
     {"primary": "#1565C0", "text": "#1A1A1A"}),
    ("22222222-2222-4222-8222-222222222202", "OUT",
     [{"key": "pay", "label": "پرداخت و خروج", "visible": True},
      {"key": "help", "label": "درخواست کمک نگهبان", "visible": True}],
     {"welcome": "خروج — هزینه نمایش داده می‌شود", "error": "پرداخت تأیید نشد"},
     {"primary": "#2E7D32", "text": "#1A1A1A"}),
]


def seed_sync(bind: Connection) -> tuple[int, int]:
    """هسته sync — بدون commit (تراکنش با فراخواننده)."""
    g_created = 0
    for gid, code, title, kind in GROUPS:
        if bind.execute(text("SELECT 1 FROM vehicle_groups WHERE code=:c"), {"c": code}).scalar() is None:
            bind.execute(text(
                "INSERT INTO vehicle_groups (id, code, title, membership_kind, is_active, sort_order) "
                "VALUES (:i,:c,:t,:k,true,:s)"),
                {"i": gid, "c": code, "t": title, "k": kind, "s": g_created})
            g_created += 1
    b_created = 0
    for bid, side, buttons, messages, colors in BOXES:
        if bind.execute(text("SELECT 1 FROM box_settings WHERE side=:s"), {"s": side}).scalar() is None:
            bind.execute(text(
                "INSERT INTO box_settings (id, side, is_active, buttons, messages, font_scale, colors) "
                "VALUES (:i,:s,true,:b,:m,1.0,:c)"),
                {"i": bid, "s": side,
                 "b": json.dumps(buttons, ensure_ascii=False),
                 "m": json.dumps(messages, ensure_ascii=False),
                 "c": json.dumps(colors, ensure_ascii=False)})
            b_created += 1
    return g_created, b_created


async def main() -> None:
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        created = await db.run_sync(lambda s: seed_sync(s.connection()))
        await db.commit()
        print(f"groups_created={created[0]} boxes_created={created[1]}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
