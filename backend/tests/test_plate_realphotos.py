"""تست رگرسیون تشخیص با عکس‌های واقعی کاربر (سه خودروی گزارش‌شده).

عکس‌ها از اسکرین‌شات‌های واقعی کاربر استخراج شده‌اند (tests/data/):
  * car1_closeup     — پلاک در دست، نمای نزدیک و کج (۱۳ ب ۱۱۱ | ۱۰)
  * car2_street_206  — پژو سفید در خیابان، پلاک ~۲۰ پیکسل (۱۳ س ۱۱۱ | ۱۱)
  * car3_samand_rear — سمند سفید، پلاک سفید روی بدنه سفید (۱۴ ب ۵۹۱ | ۷۲)

شکست‌های تاریخی این سه عکس:
  * car1: ماسک سفید دیوار/دست را برمی‌گرفت → OCR کل-تصویر ۱۰ تا ۴۰ ثانیه
  * car2/car3: ماسک سفید بدنهٔ ماشین را می‌گرفت → «پلاک یافت نشد» / خوانش غلط
الزام: تشخیص‌گر ترکیبی (ماسک رنگ + قاب پلاک + گروه‌بندی نویسه) جعبهٔ پلاک را
در رتبهٔ اول بدهد. این تست فقط OpenCV می‌خواهد و سریع است.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cv2  # noqa: E402

from app.modules.plate_ocr import engine  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")

# جعبهٔ واقعی پلاک (نزدیک‌ترین مستطیل به حاشیهٔ پلاک در هر عکس)
TRUTH = {
    "car1_closeup": (110, 95, 780, 290),
    "car2_street_206": (206, 163, 294, 184),
    "car3_samand_rear": (225, 187, 333, 217),
}


def _containment(box, truth) -> float:
    """چه کسری از پلاک واقعی داخل جعبهٔ تشخیص است (پوشش برای OCR کافی است)."""
    x1, y1 = max(box[0], truth[0]), max(box[1], truth[1])
    x2, y2 = min(box[2], truth[2]), min(box[3], truth[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area = max(1, (truth[2] - truth[0]) * (truth[3] - truth[1]))
    return inter / area


def _detect_boxes(img):
    reader = engine.PlateReader(models_dir="models")
    return [b for b, _w in reader._detect(img)]


def test_car1_closeup_plate_detected_first():
    img = cv2.imread(os.path.join(DATA, "car1_closeup.png"))
    assert img is not None
    boxes = _detect_boxes(img)
    cover = [_containment(b, TRUTH["car1_closeup"]) for b in boxes]
    assert cover and max(cover) > 0.70, f"پلاک پیدا نشد: {boxes} cover={cover}"
    # رتبهٔ اول — تا OCR پلاک را زود بخواند و بودجهٔ زمان نسوزد
    assert cover[0] > 0.70, f"جعبهٔ پلاک در رتبهٔ اول نیست: {cover}"


def test_car2_white_on_white_plate_detected_first():
    """پلاک سفید روی بدنهٔ سفید — قاب پلاک باید آن را پیدا کند."""
    img = cv2.imread(os.path.join(DATA, "car2_street_206.png"))
    assert img is not None
    boxes = _detect_boxes(img)
    cover = [_containment(b, TRUTH["car2_street_206"]) for b in boxes]
    assert cover and max(cover) > 0.70, f"پلاک پیدا نشد: {boxes} cover={cover}"
    assert cover[0] > 0.70, f"جعبهٔ پلاک در رتبهٔ اول نیست: {cover}"


def test_car3_white_on_white_plate_detected_first():
    img = cv2.imread(os.path.join(DATA, "car3_samand_rear.png"))
    assert img is not None
    boxes = _detect_boxes(img)
    cover = [_containment(b, TRUTH["car3_samand_rear"]) for b in boxes]
    assert cover and max(cover) > 0.70, f"پلاک پیدا نشد: {boxes} cover={cover}"
    assert cover[0] > 0.70, f"جعبهٔ پلاک در رتبهٔ اول نیست: {cover}"


def test_detect_priority_prefers_standard_aspect():
    """اولویت OCR: نسبت ابعاد نزدیک ۴٫۷۳ جلوتر از باکس‌های کشیده/مربعی."""
    assert engine._detect_priority((0, 0, 473, 100)) > engine._detect_priority((0, 0, 200, 200))
    assert engine._detect_priority((0, 0, 473, 100)) > engine._detect_priority((0, 0, 900, 100))
