"""تست‌های واحد ماژول پلاک‌خوان — بخش متنی (بدون وابستگی سنگین) + تشخیص کلاسیک."""
import pytest

from app.modules.plate_ocr import plate_text as pt

# ---------------------------------------------------------------------------
# نرمال‌سازی و اعتبارسنجی متنی
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_persian_digits_to_latin(self):
        assert pt.normalize("۱۲ب۳۴۵") == "12ب345"

    def test_arabic_digits_to_latin(self):
        assert pt.normalize("١٢ب٣٤٥") == "12ب345"

    def test_arabic_letters_fixed(self):
        assert pt.normalize("12ب345") == "12ب345"
        assert pt.normalize("12ي345") == "12ی345"  # ي عربی → ی فارسی

    def test_strips_noise(self):
        assert pt.normalize(" 12 ب - 345 ایران 67 ") == "12ب34567"
        assert pt.normalize("plate:12b345!") == "12345"  # حروف لاتین حذف می‌شوند


class TestValidate:
    def test_valid_6(self):
        t, ok = pt.validate("12ب345")
        assert ok and t == "12ب345"

    def test_valid_8(self):
        t, ok = pt.validate("12ب34567")
        assert ok and t == "12ب34567"

    def test_official_letters(self):
        for ch in pt.OFFICIAL_LETTERS:
            _, ok = pt.validate(f"12{ch}345")
            assert ok, ch

    def test_non_official_letter_invalid(self):
        _, ok = pt.validate("12ت345")  # ت جزو ۱۴ حرف رسمی پلاک نیست
        assert not ok

    def test_wrong_length_invalid(self):
        assert not pt.validate("12ب34")[1]
        assert not pt.validate("1ب345")[1]

    def test_persian_input_valid(self):
        assert pt.validate("۱۲ ب ۳۴۵ ایران ۶۷")[1]


class TestFormat:
    def test_format_6(self):
        assert pt.format_plate("12ب345") == "12 ب 345"

    def test_format_8(self):
        assert pt.format_plate("12ب34567") == "12 ب 345 | 67"


class TestEnforceFormat:
    def test_digit_letter_swap(self):
        # OCR حرف وسط را رقم خوانده: 12ب345 → "122345"؟ enforce باید حرف بگذارد
        fixed = pt.enforce_format("122345")
        assert fixed[2] in pt.LETTERS

    def test_keep_valid_unchanged(self):
        assert pt.enforce_format("12ب345") == "12ب345"


class TestSystemMapping:
    def test_to_system_6(self):
        assert pt.to_system_normalized("12ب345") == "12B345"

    def test_to_system_8(self):
        assert pt.to_system_normalized("12ب34567") == "12B345IR67"

    def test_garbage_returns_none(self):
        assert pt.to_system_normalized("abc") is None


# ---------------------------------------------------------------------------
# تشخیص کلاسیک — نیازمند opencv (سینتتیک: مستطیل سفید + متن تیره)
# ---------------------------------------------------------------------------

cv2 = pytest.importorskip("cv2")


def _make_plate_image(text="123456") -> "np.ndarray":
    """تصویر سینتتیک: زمینه خاکستری + مستطیل سفید عریض (نسبت ~4.5) + متن تیره."""
    np = pytest.importorskip("numpy")
    img = np.full((360, 640, 3), 90, np.uint8)
    x1, y1, x2, y2 = 120, 150, 520, 250
    cv2.rectangle(img, (x1, y1), (x2, y2), (250, 250, 250), -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), (20, 20, 20), 4)
    cv2.putText(img, text, (x1 + 30, y1 + 75), cv2.FONT_HERSHEY_SIMPLEX,
                1.8, (10, 10, 10), 6, cv2.LINE_AA)
    return img


class TestClassicalDetect:
    def test_finds_synthetic_plate(self):
        from app.modules.plate_ocr.engine import _classical_detect
        boxes = _classical_detect(_make_plate_image())
        assert len(boxes) >= 1
        x1, y1, x2, y2 = boxes[0]
        # جعبه باید حدود ناحیه پلاک باشد (با تلورانس)
        assert x1 < 180 and y1 < 190 and x2 > 460 and y2 > 210

    def test_aspect_filter(self):
        from app.modules.plate_ocr.engine import _classical_detect
        img = _make_plate_image()
        for box in _classical_detect(img):
            aspect = (box[2] - box[0]) / max(box[3] - box[1], 1.0)
            assert 2.2 <= aspect <= 7.5


class TestColorDetect:
    def test_white_plate(self):
        from app.modules.plate_ocr.engine import detect_plate_color
        np = pytest.importorskip("numpy")
        crop = np.full((60, 260, 3), 235, np.uint8)
        color, _ = detect_plate_color(crop)
        assert color in ("white", "unknown")

    def test_yellow_plate(self):
        from app.modules.plate_ocr.engine import detect_plate_color
        np = pytest.importorskip("numpy")
        crop = np.full((60, 260, 3), (0, 200, 230), np.uint8)  # BGR زرد
        color, _ = detect_plate_color(crop)
        assert color == "yellow"


class TestTextualPipeline:
    """بدون OCR واقعی — فقط مسیر متن: validate/enforce/to_system روی نمونه‌های واقعی."""

    @pytest.mark.parametrize("raw,expect_valid", [
        ("22د۱۲۳", True),
        ("36ط54711", True),
        ("99ق000", True),
        ("12345", False),
        ("", False),
    ])
    def test_samples(self, raw, expect_valid):
        assert pt.validate(raw)[1] is expect_valid


class TestCanonicalOrder:
    """راند ۴ — مرتب‌سازی دفاعی کاندیداهای معکوس RTL (نمونه‌های واقعی کارفرما)."""

    @pytest.mark.parametrize("raw,expected", [
        # قانونی — دست‌نخورده
        ("77د976", "77 د 976"),
        ("52د034", "52 د 034"),
        ("19ط382", "19 ط 382"),
        ("77د97646", "77 د 976 | 46"),
        # معکوس RTL — نمونه‌های اسکرین‌شات‌های اکتبر ۲۰۲۶
        ("976د77", "77 د 976"),        # پلاک سبز ۷۷ د ۹۷۶
        ("288ل12", "12 ل 288"),        # پلاک موقت ۱۲ ل ۲۸۸
        ("976د7746", "77 د 976 | 46"),
        ("46976د77", "77 د 976 | 46"),
    ])
    def test_format_plate_reorder(self, raw, expected):
        assert pt.format_plate(raw) == expected

    @pytest.mark.parametrize("raw,expected", [
        ("77د97646", "77D976IR46"),
        ("976د7746", "77D976IR46"),
        ("46976د77", "77D976IR46"),
        ("288ل12", "12L288"),
    ])
    def test_system_reorder(self, raw, expected):
        assert pt.to_system_normalized(raw) == expected

    def test_canonical_passthrough(self):
        # ورودی از قبل قانونی نباید هیچ تغییری کند
        assert pt._canonical_order("77د97646") == "77د97646"
        assert pt._canonical_order("12ب345") == "12ب345"
