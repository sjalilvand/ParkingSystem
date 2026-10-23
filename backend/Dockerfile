FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ---------------------------------------------------------------------------
# وابستگی‌های اختیاری پلاک‌خوان (OCR):
#   پیش‌فرض false → تصویر سبک؛ اپ بدون cv2/numpy هم بوت می‌شود
#   (graceful degradation — وضعیت از GET /api/v1/plate-ocr/status)
#   فعال‌سازی: INSTALL_OCR=true در .env.prod سپس build مجدد backend
#   (نکته: بار اول اجرا، EasyOCR مدل‌هایش را در /root/.EasyOCR دانلود می‌کند —
#    volume «easyocr» این پوشه را ماندگار می‌کند.)
# ---------------------------------------------------------------------------
ARG INSTALL_OCR=false
COPY requirements.txt requirements-ocr.txt* ./
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$INSTALL_OCR" = "true" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
        && rm -rf /var/lib/apt/lists/* \
        && pip install --no-cache-dir -r requirements-ocr.txt; \
    fi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
