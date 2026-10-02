"""Seed پیش‌فرض‌های پیکربندی — idempotent، منبع واحد (migration/تست/دستی)."""
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
     [{"key": "submit", "label": "ارسال رویداد دوربین", "visible": True},
      {"key": "yard_request", "label": "درخواست پارک در محوطه", "visible": True},
      {"key": "own_parking", "label": "پارکینگ خودم", "visible": True},
      {"key": "help", "label": "کمک نگهبان", "visible": True}],
     {"welcome": "خوش آمدید — پلاک خود را وارد یا منتظر بمانید", "error": "خطا — به نگهبان مراجعه کنید"},
     {"primary": "#1565C0", "text": "#1A1A1A"}),
    ("22222222-2222-4222-8222-222222222202", "OUT",
     [{"key": "submit", "label": "ارسال رویداد دوربین", "visible": True},
      {"key": "pay", "label": "ثبت پرداخت", "visible": True},
      {"key": "help", "label": "درخواست کمک نگهبان", "visible": True}],
     {"welcome": "خروج — هزینه نمایش داده می‌شود", "error": "پرداخت تأیید نشد"},
     {"primary": "#2E7D32", "text": "#1A1A1A"}),
]

RECEIPTS = [
    ("33333333-3333-4333-8333-333333333301", "قبض پیش‌فرض ورود/خروج", True, 80,
     [{"key": "complex_name", "visible": True}, {"key": "receipt_id", "visible": True},
      {"key": "plate", "visible": True}, {"key": "entry_time", "visible": True},
      {"key": "parking_spot", "visible": True}, {"key": "tariff_summary", "visible": True},
      {"key": "trial_badge", "visible": True}, {"key": "qr", "visible": False},
      {"key": "guide_text", "visible": True}],
     "مجتمع مسکونی ارکیده", "لطفاً پیش از خروج تسویه کنید."),
]


def seed_sync(bind: Connection) -> tuple[int, int, int]:
    """هسته sync — بدون commit (تراکنش با فراخواننده)."""
    g = 0
    for gid, code, title, kind in GROUPS:
        if bind.execute(text("SELECT 1 FROM vehicle_groups WHERE code=:c"), {"c": code}).scalar() is None:
            bind.execute(text(
                "INSERT INTO vehicle_groups (id, code, title, membership_kind, is_active, sort_order) "
                "VALUES (:i,:c,:t,:k,true,:s)"),
                {"i": gid, "c": code, "t": title, "k": kind, "s": g})
            g += 1
    b = 0
    for bid, side, buttons, messages, colors in BOXES:
        if bind.execute(text("SELECT 1 FROM box_settings WHERE side=:s"), {"s": side}).scalar() is None:
            bind.execute(text(
                "INSERT INTO box_settings (id, side, is_active, buttons, messages, font_scale, colors) "
                "VALUES (:i,:s,true,:b,:m,1.0,:c)"),
                {"i": bid, "s": side,
                 "b": json.dumps(buttons, ensure_ascii=False),
                 "m": json.dumps(messages, ensure_ascii=False),
                 "c": json.dumps(colors, ensure_ascii=False)})
            b += 1
    r = 0
    for rid, name, active, width, sections, header, footer in RECEIPTS:
        if bind.execute(text("SELECT 1 FROM receipt_templates WHERE id=:i"), {"i": rid}).scalar() is None:
            bind.execute(text(
                "INSERT INTO receipt_templates (id, name, is_active, paper_width_mm, sections, header_text, footer_text, show_trial_badge) "
                "VALUES (:i,:n,:a,:w,:sec,:h,:f,true)"),
                {"i": rid, "n": name, "a": active, "w": width,
                 "sec": json.dumps(sections, ensure_ascii=False), "h": header, "f": footer})
            r += 1
    return g, b, r


async def main() -> None:
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        created = await db.run_sync(lambda s: seed_sync(s.connection()))
        await db.commit()
        print(f"groups={created[0]} boxes={created[1]} receipts={created[2]}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
