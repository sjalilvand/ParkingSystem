"""ماژول پلاک‌خوان (OCR) — تشخیص و خواندن پلاک ایران از تصویر.

ساختار:
  plate_text.py  ابزارهای متنی (نرمال‌سازی/اعتبارسنجی/قالب)
  engine.py      موتور تشخیص + OCR (YOLO/کلاسیک + CRNN/EasyOCR)
  router.py      API: status / read / test-page
  static/        صفحه تست آپلود تصویر (mount روی /plate-test)
"""
