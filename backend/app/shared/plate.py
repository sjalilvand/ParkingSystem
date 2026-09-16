import re

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_ENGLISH_DIGITS = "0123456789"

DIGIT_TRANS = str.maketrans(_PERSIAN_DIGITS + _ARABIC_DIGITS, _ENGLISH_DIGITS + _ENGLISH_DIGITS)
ARABIC_LETTER_TRANS = str.maketrans({"ك": "ک", "ي": "ی", "ى": "ی"})

LETTER_MAP = {
    "ا": "A", "ب": "B", "پ": "P", "ت": "T", "ث": "S", "ج": "J", "چ": "C",
    "ح": "H", "خ": "X", "د": "D", "ذ": "Z", "ر": "R", "ز": "Z", "ژ": "Z",
    "س": "S", "ش": "S", "ص": "S", "ض": "Z", "ط": "T", "ظ": "Z", "ع": "A",
    "غ": "G", "ف": "F", "ق": "G", "ک": "K", "گ": "G", "ل": "L", "م": "M",
    "ن": "N", "و": "V", "ه": "H", "ی": "Y",
}

PLATE_REGEX = re.compile(r"^(\d{2})(.+?)(\d{3})(?:IR)?(\d{2})?$")
VALID_PLATE_REGEX = re.compile(r"^\d{2}[A-Z]{1,2}\d{3}(IR\d{2})?$")


def normalize_plate(raw: str | None) -> str | None:
    """نرمال‌سازی پلاک ایرانی. مثال: ۱۲ ب ۳۴۵ ایران ۶۷ -> 12B345IR67"""
    if not raw or not raw.strip():
        return None

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
        if ch in LETTER_MAP:
            normalized_letters += LETTER_MAP[ch]
        elif ch.isascii() and ch.isalpha():
            normalized_letters += ch
    if not normalized_letters:
        normalized_letters = "X"

    result = f"{two_digits}{normalized_letters}{three_digits}"
    if province:
        result += f"IR{province}"
    return result


def is_valid_iranian_plate(normalized: str | None) -> bool:
    if not normalized:
        return False
    return bool(VALID_PLATE_REGEX.match(normalized))