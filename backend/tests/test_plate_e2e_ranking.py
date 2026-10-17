"""تست سرتاسری رتبه‌بندی — بازسازی دقیق سناریوی کاربر:
عکس نزدیک + OCR ضعیف (متن ۷ نویسه‌ای «۱۳۸۸۱۱۸»، اطمینان ۵۶٪) → باید «۱۳ب۱۱۸» برتر شود.
همچنین: fast_mode باید OCR کل-تصویر را رد کند (رفع کندی ۳۷ ثانیه).
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402
import cv2  # noqa: E402

from app.modules.plate_ocr.engine import PlateReader  # noqa: E402


def _img_closeup() -> np.ndarray:
    W, H = 1200, 900
    img = np.full((H, W, 3), (70, 60, 55), np.uint8)
    ph = int(H * 0.42)
    pw = int(ph * 3.0)
    x0, y0 = (W - pw) // 2, (H - ph) // 2
    plate = np.full((ph, pw, 3), (245, 245, 245), np.uint8)
    cv2.rectangle(plate, (0, 0), (pw - 1, ph - 1), (40, 40, 40), 6)
    img[y0:y0 + ph, x0:x0 + pw] = plate
    return img


def test_user_scenario_ranking(monkeypatch=None):
    r = PlateReader(models_dir="models")
    # شبیه‌سازی OCR ضعیف روی برش — همان خروجیِ واقعی کاربر
    r._ocr_crop = lambda crop, *a, **k: [("1388118", 0.56, "easyocr")]
    res = r.read_image(_img_closeup(), min_conf=0.25, want_annotated=False)
    assert res["success"], "no candidates at all"
    best = res["best"]
    assert best["valid"], f"best invalid: {best}"
    assert best["raw"] == "13ب118", f"expected 13ب118, got {best['raw']}"
    assert best["system"], "system normalized empty"
    print(f"best: {best['raw']} → {best['system']}  (conf {best['confidence']})")
    # در fast_mode با وجود کاندیدا، OCR کل-تصویر رد شده باشد
    assert res["engine"]["fullimage_skipped"], "fast-mode should skip fullimage OCR"
    assert res["engine"]["timings"]["fullimage_ms"] == 0
    print("timings:", res["engine"]["timings"])


def test_slow_mode_runs_fullimage(monkeypatch=None):
    r = PlateReader(models_dir="models")
    # هیچ OCRای نتیجه نمی‌دهد → حالت کند باید OCR کل تصویر را امتحان کند
    r._ocr_crop = lambda crop, *a, **k: []
    t0 = time.perf_counter()
    res = r.read_image(_img_closeup(), min_conf=0.25,
                       want_annotated=False, fast_mode=False)
    ms = (time.perf_counter() - t0) * 1000
    assert res["engine"]["fullimage_skipped"] is None
    print(f"slow mode ran (incl. real full-image attempt on mock OCR): {ms:.0f}ms")


if __name__ == "__main__":
    t0 = time.perf_counter()
    test_user_scenario_ranking()
    test_slow_mode_runs_fullimage()
    print(f"\ne2e tests passed in {(time.perf_counter() - t0) * 1000:.0f}ms")
