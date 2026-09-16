from app.shared.plate import is_valid_iranian_plate, normalize_plate


def test_normalize_persian_standard():
    assert normalize_plate("۱۲ ب ۳۴۵ ایران ۶۷") == "12B345IR67"


def test_normalize_latin():
    assert normalize_plate("12 B 345 Iran 67") == "12B345IR67"


def test_normalize_without_province():
    assert normalize_plate("12ب345") == "12B345"


def test_invalid_plate_returns_none():
    assert normalize_plate("hello world") is None


def test_valid_check():
    assert is_valid_iranian_plate("12B345IR67") is True
    assert is_valid_iranian_plate("ABC") is False