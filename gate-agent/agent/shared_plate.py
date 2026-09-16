import re

_DIGITS = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"
_TRANS = str.maketrans(_DIGITS, "01234567890123456789")
_LETTERS = {
    "ا": "A", "ب": "B", "پ": "P", "ت": "T", "ث": "S", "ج": "J", "چ": "C",
    "ح": "H", "خ": "X", "د": "D", "ذ": "Z", "ر": "R", "ز": "Z", "ژ": "Z",
    "س": "S", "ش": "S", "ص": "S", "ض": "Z", "ط": "T", "ظ": "Z", "ع": "A",
    "غ": "G", "ف": "F", "ق": "G", "ک": "K", "گ": "G", "ل": "L", "م": "M",
    "ن": "N", "و": "V", "ه": "H", "ی": "Y",
}
_REGEX = re.compile(r"^(\d{2})(.+?)(\d{3})(?:IR)?(\d{2})?$")


def normalize_plate(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    text = raw.strip().translate(_TRANS).upper()
    text = re.sub(r"[\s\-_/\\.,()]+", "", text)
    text = text.replace("IRAN", "IR").replace("ایران", "IR")
    m = _REGEX.search(text)
    if not m:
        return None
    two, letters, three, province = m.groups()
    norm = "".join(_LETTERS.get(ch, ch) for ch in letters if ch in _LETTERS or (ch.isascii() and ch.isalpha())) or "X"
    result = f"{two}{norm}{three}"
    if province:
        result += f"IR{province}"
    return result