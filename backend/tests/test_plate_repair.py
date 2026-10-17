"""تست بازسازی متن‌های خراب OCR — سناریوی واقعی «ب» → «۸» (۱۳ب۱۱۸ → ۱۳۸۸۱۱۸)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.modules.plate_ocr import plate_text as pt  # noqa: E402


def test_real_case_13b118():
    """متن خراب واقعی کاربر: ۱۳ب۱۱۸ خوانده شد ۱۳۸۸۱۱۸ (۷ نویسه) → باید ۱۳ب۱۱۸ ترمیم شود."""
    repairs = pt.repair_candidates("1388118")
    texts = [t for t, _ in repairs]
    assert "13ب118" in texts, f"13ب118 in repairs? got {texts[:10]}"
    # همهٔ ترمیم‌ها باید قالب معتبر داشته باشند
    for t, mul in repairs:
        _, valid = pt.validate(t)
        assert valid, f"repair produced invalid {t}"
        assert 0 < mul <= 1


def test_direct_deletion():
    """حرف سالم + نویسهٔ اضافه: ۱۳ب۱۱۸۸ → حذف نویسهٔ آخر → ۱۳ب۱۱۸ با اطمینان بالا."""
    repairs = pt.repair_candidates("13ب1188")
    assert ("13ب118", pt.REPAIR_DEL_CONF) in repairs


def test_normalize_variants():
    assert pt.normalize("۱۳ب۱۱۸") == "13ب118"
    assert pt.normalize("13 B 118") == "13B118" if "B" in pt.LETTERS else True
    # حرف غیررسمی حذف می‌شود
    assert pt.normalize("13پ118") == "13118"


def test_validate_and_enforce():
    assert pt.validate("13ب118")[1] is True
    assert pt.validate("1388118")[1] is False          # ۷ نویسه — نامعتبر
    assert pt.validate("13ب11810")[1] is True          # با کد استان = ۸ نویسه
    # ۶ نویسهٔ رقم‌خالص → enforce حرف وسط می‌سازد
    fixed = pt.enforce_format("138118")
    assert len(fixed) == 6 and fixed[2] in pt.LETTERS and fixed != "138118"


def test_system_format():
    sys1 = pt.to_system_normalized("13ب118")
    assert sys1 is not None and sys1.startswith("13")
    sys2 = pt.to_system_normalized("13ب11810")
    assert sys2 is not None and "IR10" in sys2.upper()


def test_repair_no_false_for_valid():
    """متن سالم نباید کاندیدای ترمیم تولید کند."""
    assert pt.repair_candidates("13ب118") == []
    assert pt.repair_candidates("13ب11810") == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
