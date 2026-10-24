"""ماژول دوربین‌های گیت — سناریو A (ANPR) و سناریو B (RTSP + OCR داخلی)."""
import os

# RTSP پایدار: حمل TCP + مهلت اتصال ۸ ثانیه (میلی‌ثانیه در stimeout)
# بدون این، cv2 روی دوربینِ در دسترس‌ناپذیر تا ~۳۰ ثانیه قفل می‌کند.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;8000000|max_delay;2000000",
)
