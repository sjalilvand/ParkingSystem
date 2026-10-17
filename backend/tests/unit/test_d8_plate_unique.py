"""تست‌های D8 — نگاشت حروف پلاک (MANY_TO_ONE وضع موجود / UNIQUE یکتا)."""
from app.shared.plate import (
    LETTER_MAP,
    UNIQUE_LETTER_MAP,
    get_letter_map,
    is_valid_iranian_plate,
    normalize_plate,
    remap_normalized_plate,
)


def test_d8_default_is_many_to_one():
    # رفتار قبلی بدون پارامتر: س/ش/ص/ث همه -> S
    assert get_letter_map(None) is LETTER_MAP
    assert normalize_plate("۱۲ س ۳۴۵") == "12S345"
    assert normalize_plate("۱۲ ش ۳۴۵") == "12S345"


def test_d8_unique_map_values_all_distinct():
    values = list(UNIQUE_LETTER_MAP.values())
    assert len(values) == len(set(values)), "نگاشت یکتا باید 1:1 باشد"


def test_d8_unique_map_covers_persian_letters():
    # کل حروف MANY_TO_ONE باید در UNIQUE هم پوشش داده شوند
    assert set(LETTER_MAP.keys()) == set(UNIQUE_LETTER_MAP.keys())


def test_d8_unique_normalization():
    assert normalize_plate("۱۲ س ۳۴۵", letter_mapping="UNIQUE") == "12S345"
    assert normalize_plate("۱۲ ش ۳۴۵", letter_mapping="UNIQUE") == "12SH345"
    assert normalize_plate("۱۲ ص ۳۴۵", letter_mapping="UNIQUE") == "12SC345"
    assert normalize_plate("۱۲ ق ۳۴۵", letter_mapping="UNIQUE") == "12G345"
    assert normalize_plate("۱۲ گ ۳۴۵", letter_mapping="UNIQUE") == "12GG345"


def test_d8_unique_produces_valid_plates():
    for fa, code in UNIQUE_LETTER_MAP.items():
        plate = f"12{fa}345ایران67"
        normalized = normalize_plate(plate, letter_mapping="UNIQUE")
        assert normalized == f"12{code}345IR67", f"failed for {fa}"
        assert is_valid_iranian_plate(normalized), f"invalid plate for {fa}"


def test_d8_full_plate_with_province_unique():
    assert normalize_plate("۱۲ ب ۳۴۵ ایران ۶۷", letter_mapping="UNIQUE") == "12B345IR67"


def test_d8_remap_unique_to_many_to_one_roundtrip():
    # UNIQUE -> MANY_TO_ONE چون مبدا یکتاست، همیشه قابل تبدیل است
    assert remap_normalized_plate("12SH345", UNIQUE_LETTER_MAP, LETTER_MAP) == "12S345"
    assert remap_normalized_plate("12GG345IR67", UNIQUE_LETTER_MAP, LETTER_MAP) == "12G345IR67"


def test_d8_remap_many_to_one_to_unique_ambiguous_returns_none():
    # S در MANY_TO_ONE به ۴ حرف می‌رسد -> تبدیل یکتا ممکن نیست
    assert remap_normalized_plate("12S345", LETTER_MAP, UNIQUE_LETTER_MAP) is None
    # Z نیز مبهم است (ذ/ز/ژ/ض/ظ)
    assert remap_normalized_plate("12Z345", LETTER_MAP, UNIQUE_LETTER_MAP) is None
    # B یکتاست (فقط ب) -> قابل تبدیل
    assert remap_normalized_plate("12B345", LETTER_MAP, UNIQUE_LETTER_MAP) == "12B345"


def test_d8_remap_invalid_plate_returns_none():
    assert remap_normalized_plate("garbage", LETTER_MAP, UNIQUE_LETTER_MAP) is None
    assert remap_normalized_plate(None, LETTER_MAP, UNIQUE_LETTER_MAP) is None


def test_d8_normalize_none_and_empty():
    assert normalize_plate(None) is None
    assert normalize_plate("") is None
    assert normalize_plate("   ") is None
