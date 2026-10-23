"""رگرسیون بحرانی استقرار: اپ باید بدون وابستگی‌های سنگین OCR هم import شود.

خطای واقعی تولید (۵۰۲ برای همهٔ endpoint ها):
  bootstrap_prod → import app.main → plate_ocr/router.py
  → «ModuleNotFoundError: No module named 'cv2'» → uvicorn هرگز بوت نشد.

تصویر Docker عمداً سبک است (requirements.txt بدون opencv/numpy/easyocr) و
وابستگی‌های OCR اختیاری‌اند — پس بوت نباید به آن‌ها وابسته باشد (graceful
degradation). این تست همان مسیر خطا را در زیرپروسه‌ای با import-blocker
بازتولید می‌کند.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]

_BLOCKER = """\
import sys


class _BlockHeavyDeps:
    \"\"\"هر import ماژول‌های سنگین/اختیاری OCR را با ImportError مسدود می‌کند.\"\"\"

    BLOCKED = {"cv2", "numpy", "easyocr", "torch", "ultralytics"}

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in self.BLOCKED:
            raise ImportError(f"blocked for regression test: {fullname}")
        return None


sys.meta_path.insert(0, _BlockHeavyDeps())

import app.main  # noqa: E402

from app.modules.plate_ocr import router as plate_router  # noqa: E402

assert plate_router.HAS_OCR_DEPS is False, "بلاکر کار نمی‌کند — cv2/numpy لود شدند؟"

caps = plate_router.capabilities("models")
assert caps["numpy"] is False and caps["opencv"] is False, caps

print("APP_IMPORT_OK")
"""


def test_app_imports_without_ocr_deps():
    """بدون cv2/numpy/easyocr/torch هم app.main باید کامل لود شود."""
    # env ایزوله — تا DATABASE_URL بیرونی (میزبان/CI) در import دخالت نکند
    env = {
        k: v for k, v in os.environ.items()
        if k not in {"DATABASE_URL", "SIM_DATABASE_URL"}
    }
    env["DATABASE_URL"] = "sqlite+aiosqlite:///./_regression_ut.db"
    proc = subprocess.run(
        [sys.executable, "-c", _BLOCKER],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    assert proc.returncode == 0, (
        "import app.main بدون وابستگی‌های OCR شکست خورد — فاجعهٔ بوت تولید!\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    assert "APP_IMPORT_OK" in proc.stdout
