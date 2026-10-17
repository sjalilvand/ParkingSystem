import re

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_ENGLISH_DIGITS = "0123456789"

DIGIT_TRANS = str.maketrans(_PERSIAN_DIGITS + _ARABIC_DIGITS, _ENGLISH_DIGITS + _ENGLISH_DIGITS)
ARABIC_LETTER_TRANS = str.maketrans({"ك": "ک", "ي": "ی", "ى": "ی"})

# ---------------------------------------------------------------------------
# D8 (F18) — نگاشت حروف پلاک به لاتین:
#   MANY_TO_ONE (وضع موجود / حفظ وضعیت): چند حرف فارسی به یک حرف لاتین —
#     مثلاً س/ش/ص/ث→S و ق/گ→G. کدگذاری از دست نمی‌رود اما نگاشت برگشت‌پذیر نیست.
#   UNIQUE (نگاشت یکتا): هر حرف فارسی به یک کد لاتینِ ۱-۲ حرفیِ یکتا —
#     برگشت‌پذیر است؛ برای فعال‌سازی، migration پلاک‌های موجود الزامی است
#     (scripts/migrate_plate_letters.py) و سپس PLATE_LETTER_MAPPING=UNIQUE.
# ---------------------------------------------------------------------------
LETTER_MAP = {
    "ا": "A", "ب": "B", "پ": "P", "ت": "T", "ث": "S", "ج": "J", "چ": "C",
    "ح": "H", "خ": "X", "د": "D", "ذ": "Z", "ر": "R", "ز": "Z", "ژ": "Z",
    "س": "S", "ش": "S", "ص": "S", "ض": "Z", "ط": "T", "ظ": "Z", "ع": "A",
    "غ": "G", "ف": "F", "ق": "G", "ک": "K", "گ": "G", "ل": "L", "م": "M",
    "ن": "N", "و": "V", "ه": "H", "ی": "Y",
}

# نگاشت یکتا (۱:۱) — مقادیر همگی متمایز؛ بازه [A-Z]{1,2} با VALID_PLATE_REGEX سازگار است.
UNIQUE_LETTER_MAP = {
    "ا": "A", "ب": "B", "پ": "P", "ت": "T", "ث": "SS", "ج": "J", "چ": "CC",
    "ح": "H", "خ": "KH", "د": "D", "ذ": "ZD", "ر": "R", "ز": "Z", "ژ": "ZJ",
    "س": "S", "ش": "SH", "ص": "SC", "ض": "ZB", "ط": "TA", "ظ": "ZZ", "ع": "E",
    "غ": "GH", "ف": "F", "ق": "G", "ک": "K", "گ": "GG", "ل": "L", "م": "M",
    "ن": "N", "و": "V", "ه": "HH", "ی": "Y",
}

PLATE_MODES = ("MANY_TO_ONE", "UNIQUE")


def get_letter_map(mode: str | None = None) -> dict:
    """D8: انتخاب جدول نگاشت حروف. پیش‌فرض MANY_TO_ONE (حفظ وضعیت)."""
    if (mode or "").upper() == "UNIQUE":
        return UNIQUE_LETTER_MAP
    return LETTER_MAP


PLATE_REGEX = re.compile(r"^(\d{2})(.+?)(\d{3})(?:IR)?(\d{2})?$")
VALID_PLATE_REGEX = re.compile(r"^\d{2}[A-Z]{1,2}\d{3}(IR\d{2})?$")
# پلاک نرمال‌شده استاندارد: ۲ رقم + کد حرف + ۳ رقم (+ استان)
NORMALIZED_PARTS_REGEX = re.compile(r"^(\d{2})([A-Z]{1,2})(\d{3})(IR(\d{2}))?$")


def normalize_plate(raw: str | None, letter_mapping: str | None = None) -> str | None:
    """نرمال‌سازی پلاک ایرانی. مثال: ۱۲ ب ۳۴۵ ایران ۶۷ -> 12B345IR67

    letter_mapping: "MANY_TO_ONE" (پیش‌فرض، وضع موجود) | "UNIQUE" (نگاشت یکتا D8).
    اگر None باشد از تنظیمات (settings.PLATE_LETTER_MAPPING) خوانده می‌شود.
    """
    if not raw or not raw.strip():
        return None

    if letter_mapping is None:
        try:
            from app.core.config import settings
            letter_mapping = getattr(settings, "PLATE_LETTER_MAPPING", "MANY_TO_ONE")
        except Exception:
            letter_mapping = "MANY_TO_ONE"
    letter_map = get_letter_map(letter_mapping)

    text = raw.strip()
    text = text.translate(DIGIT_TRANS)
    text = text.translate(ARABIC_LETTER_TRANS)
    text = text.upper()
    text = re.sub(r"[\s\-_/\\.,()]+", "", text)
    text = text.replace("IRAN", "IR").replace("ایران", "IR")

    match = PLATE_REGEX.search(text)
    if not match:
        return None

    two_digits, letters, three_digits, province = match.groups()

    normalized_letters = ""
    for ch in letters:
        if ch in letter_map:
            normalized_letters += letter_map[ch]
        elif ch.isascii() and ch.isalpha():
            normalized_letters += ch
    if not normalized_letters:
        normalized_letters = "X"

    result = f"{two_digits}{normalized_letters}{three_digits}"
    if province:
        result += f"IR{province}"
    return result


def remap_normalized_plate(normalized: str, from_map: dict, to_map: dict) -> str | None:
    """D8: تبدیل پلاکِ نرمال‌شده از یک جدول نگاشت به جدول دیگر (برای migration پلاک‌ها).

    مثال: MANY_TO_ONE→UNIQUE برای "12B345IR67": حرف B در from_map حروف فارسی
    متعددی (ب/پ/...) را پوشش می‌دهد؛ برای بازسازی یکتا، حرف مبنا از reverse
    جدول مبدأ استخراج و در جدول مقصد نگاشت می‌شود.
    پلاک‌هایی که معادل یکتا ندارند (حرف مبدأ چند-به-یک) قابل تبدیل برگشت‌پذیر
    نیستند و None برمی‌گردند (مهاجرت آن‌ها نیازمند رجوع به plate_raw است).
    """
    if not normalized:
        return None
    m = NORMALIZED_PARTS_REGEX.match(normalized)
    if not m:
        return None
    two_digits, letters, three_digits, _ir, province = m.groups()
    reverse_from: dict[str, list] = {}
    for fa, lat in from_map.items():
        reverse_from.setdefault(lat, []).append(fa)
    candidates = reverse_from.get(letters, [])
    # یکتا فقط وقتی قابل بازیابی است که دقیقاً یک حرف فارسی به این کد می‌رسد
    if len(candidates) != 1:
        return None
    fa_letter = candidates[0]
    new_code = to_map.get(fa_letter)  # to_map از قبل fa->lat است
    if not new_code:
        return None
    result = f"{two_digits}{new_code}{three_digits}"
    if province:
        result += f"IR{province}"
    return result


def is_valid_iranian_plate(normalized: str | None) -> bool:
    if not normalized:
        return False
    return bool(VALID_PLATE_REGEX.match(normalized))
