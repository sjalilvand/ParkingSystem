"""تست تشخیص پلاک در عکس نزدیک — رگرسیون باگ «سقف ارتفاع ۰٫۳۵» (۳۷ ثانیه → مسیر برش)."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402
import cv2  # noqa: E402

from app.modules.plate_ocr.engine import _classical_detect  # noqa: E402


def synth_closeup_plate() -> np.ndarray:
    """عکس شبیه واقعی: پلاک سفید عریض که ~۴۲٪ ارتفاع کادر را گرفته (نمای نزدیک)."""
    W, H = 1200, 900
    img = np.full((H, W, 3), (70, 60, 55), np.uint8)          # پس‌زمینه تیره
    ph = int(H * 0.42)                                         # ۳۷۸ پیکسل — بالای سقف قدیمیِ ۰٫۳۵
    pw = int(ph * 3.0)                                         # نسبت ~۳ (نزدیک‌تر از حالت استاندارد)
    x0, y0 = (W - pw) // 2, (H - ph) // 2
    plate = np.full((ph, pw, 3), (245, 245, 245), np.uint8)
    cv2.rectangle(plate, (0, 0), (pw - 1, ph - 1), (40, 40, 40), 6)
    cv2.putText(plate, "138118", (pw // 10, int(ph * 0.75)),
                cv2.FONT_HERSHEY_SIMPLEX, pw / 160.0, (20, 20, 20), max(2, ph // 12))
    img[y0:y0 + ph, x0:x0 + pw] = plate
    return img


def synth_cropped_plate() -> np.ndarray:
    """پلاکِ نزدیک که از کادر بیرون زده — نسبت ~۱٫۹ (قدیمی‌تر از حد فیلتر بود)."""
    W, H = 1200, 900
    img = np.full((H, W, 3), (70, 60, 55), np.uint8)
    ph, pw = int(H * 0.55), int(H * 0.55 * 1.9)               # ۴۹۵×۹۴۰
    x0, y0 = (W - pw) // 2, (H - ph) // 2
    plate = np.full((ph, pw, 3), (245, 245, 245), np.uint8)
    cv2.rectangle(plate, (0, 0), (pw - 1, ph - 1), (40, 40, 40), 6)
    img[y0:y0 + ph, x0:x0 + pw] = plate
    return img


def synth_far_plate() -> np.ndarray:
    """عکس از دور — پلاک کوچک (~۸٪ ارتفاع) برای اطمینان از نشکستن حالت عادی."""
    W, H = 1600, 900
    img = np.full((H, W, 3), (80, 75, 70), np.uint8)
    ph, pw = int(H * 0.08), int(W * 0.10)
    x0, y0 = W // 3, H // 2
    plate = np.full((ph, pw, 3), (245, 245, 245), np.uint8)
    cv2.rectangle(plate, (0, 0), (pw - 1, ph - 1), (40, 40, 40), 2)
    img[y0:y0 + ph, x0:x0 + pw] = plate
    return img


def test_closeup_detected():
    boxes = _classical_detect(synth_closeup_plate())
    assert boxes, "close-up plate NOT detected — regression!"
    x1, y1, x2, y2 = boxes[0]
    h_img = 900
    box_h = y2 - y1
    assert box_h > h_img * 0.4, f"box too small: {box_h}"
    print(f"close-up: box={boxes[0]} height_ratio={box_h / h_img:.2f}")


def test_cropped_detected():
    boxes = _classical_detect(synth_cropped_plate())
    assert boxes, "partially-out-of-frame plate NOT detected — regression!"
    print(f"cropped: box={boxes[0]}")


def test_far_still_detected():
    boxes = _classical_detect(synth_far_plate())
    assert boxes, "far plate NOT detected — regression!"
    print(f"far: box={boxes[0]}")


if __name__ == "__main__":
    t0 = time.perf_counter()
    test_closeup_detected()
    test_cropped_detected()
    test_far_still_detected()
    print(f"\ndetection tests passed in {(time.perf_counter() - t0) * 1000:.0f}ms")
