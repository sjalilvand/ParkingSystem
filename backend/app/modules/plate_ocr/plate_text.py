"""ابزارهای متنی پلاک ایران — نرمال‌سازی، اعتبارسنجی، قالب‌بندی.

برگرفته از plate_all.py (پلاک‌خوان ایرانی v3) و هم‌ساز با app/shared/plate.py
(نگاشت حروف به لاتین برای ذخیره‌سازی در سیستم پارکینگ).

قالب پلاک ایران: ۲ رقم + ۱ حرف + ۳ رقم (+ ۲ رقم کد استان بعد از «ایران»)
مثال: ۱۲ ب ۳۴۵ ایران ۶۷
"""
import re

DIGITS = "0123456789"

# ۱۴ حرف رسمی روی پلاک‌های ایران (بر اساس استاندارد پلاک‌بندی)
OFFICIAL_LETTERS = "بجدسصطعقلمنوهی"
LETTERS = OFFICIAL_LETTERS

# برای OCR محدود کردن allowlist به همین مجموعه دقت را بالا می‌برد
OCR_ALLOWLIST = DIGITS + OFFICIAL_LETTERS

_P2E = {ord(p): str(d) for d, p in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_AR2E = {ord(a): str(d) for d, a in enumerate("٠١٢٣٤٥٦٧٨٩")}
_ARABIC_FIX = str.maketrans({"ك": "ک", "ي": "ی", "ى": "ی", "ھ": "ه", "ﻻ": "لا"})

PLATE_RE = re.compile(rf"^(\d{{2}})([{LETTERS}])(\d{{3}})(?:IR)?(\d{{2}})?$")

# نگاشت "شباهت بصری" رقم→حرف (فقط حروف رسمی) — وقتی OCR حرف وسط را رقم خوانده.
# توجه: این نگاشت هیوریستیک است؛ کاندیدای حاصل با ضریب اطمینان کمتر رتبه می‌شود.
_VIS_DIGIT_TO_LETTER = {
    "0": "ه", "1": "ل", "2": "ب", "3": "ع", "4": "ه",
    "5": "ص", "6": "ط", "7": "ن", "8": "ه", "9": "ق",
}


def normalize(text: str) -> str:
    """تبدیل ارقام فارسی/عربی به لاتین + حذف کلمه ایران + حذف نویسه‌های غیر پلاکی."""
    t = (text or "").translate(_P2E).translate(_AR2E).translate(_ARABIC_FIX)
    # کلمه «ایران» بخشی از پلاک است، نه نویسه پلاک — قبل از پاکسازی حذف شود
    t = t.replace("ایران", " ").replace("IRAN", " ").replace("Iran", " ")
    return re.sub(rf"[^\d{LETTERS}]", "", t)


def validate(text: str) -> tuple[str, bool]:
    """برمی‌گرداند (متن نرمال‌شده، معتبر بودن قالب پلاک ایران)."""
    t = normalize(text)
    return t, bool(PLATE_RE.match(t))


def format_plate(t: str) -> str:
    """قالب خوانا برای نمایش: 12B345 → «۱۲ ب ۳۴۵» (نمایش RTL در UI انجام می‌شود)."""
    t = normalize(t)
    if len(t) == 6:
        return f"{t[:2]} {t[2]} {t[3:]}"
    if len(t) == 8:
        return f"{t[:2]} {t[2]} {t[3:6]} | {t[6:]}"
    return t


def enforce_format(text: str) -> str:
    """نزدیک‌کردن متن خام OCR به قالب قانونی پلاک.

    ⚠️ نگاشت lossy است — فقط وقتی استفاده شود که اطمینان پایین و متن نامعتبر است.
    موقعیت ۲ (حرف) و بقیه ارقام بر اساس قالب ۶/۸ نویسه‌ای تصحیح می‌شوند.
    """
    t = normalize(text)
    if len(t) not in (6, 8):
        return t
    out = []
    for i, ch in enumerate(t):
        if i == 2:
            out.append(ch if ch in LETTERS else _VIS_DIGIT_TO_LETTER.get(ch, "ب"))
        else:
            out.append(ch if ch.isdigit() else "0")
    return "".join(out)


def to_system_normalized(plate_fa: str, letter_mapping: str | None = None) -> str | None:
    """تبدیل پلاک فارسیِ نرمال‌شده (مثل «12ب345» یا «12ب34567») به فرمت سیستم.

    از app/shared/plate.py استفاده می‌کند → خروجی مثل «12B345» یا «12B345IR67».
    با این فرمت می‌توان مستقیماً vehicles.plate_normalized را جستجو کرد.
    """
    if not plate_fa:
        return None
    t = normalize(plate_fa)
    if len(t) == 8:
        raw = f"{t[:2]} {t[2]} {t[3:6]} ایران {t[6:]}"
    elif len(t) == 6:
        raw = f"{t[:2]} {t[2]} {t[3:]}"
    else:
        return None
    try:
        from app.shared.plate import normalize_plate
        return normalize_plate(raw, letter_mapping=letter_mapping)
    except Exception:
        return None
