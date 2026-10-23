"""موتور پلاک‌خوان ایرانی — تشخیص پلاک + خواندن نویسه‌ها (OCR).

برگرفته از plate_all.py (پلاک‌خوان ایرانی v3) و به‌صورت سرویس برای بک‌اند
سیستم پارکینگ تطبیق داده شده است.

معماری کاهش تدریجی (graceful degradation):
  تشخیص پلاک:
    1) YOLO (اگر models/plate_det_best.pt موجود و ultralytics نصب بود)
    2) تشخیص کلاسیک CV (کانتور + نسبت ابعاد — همیشه در دسترس با OpenCV)
    3) OCR روی کل تصویر (برای عکس‌های نزدیک از پلاک)
  OCR:
    1) CRNN آموزش‌دیده (اگر models/crnn_best.pt موجود و torch نصب بود)
    2) EasyOCR (پیش‌فرض — مدل‌های آماده؛ بار اول دانلود می‌کند)

هیچ‌کدام از وابستگی‌های سنگین (easyocr/torch/ultralytics) اجباری نیستند؛
وضعیت واقعی از capabilities() و GET /api/v1/plate-ocr/status قابل مشاهده است.
"""
from __future__ import annotations

import base64
import threading
import time
from dataclasses import dataclass, field

# numpy هم مثل cv2 اختیاری است — اپ باید بدون آن هم import شود (تصویر Docker سبک)
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]
    HAS_NUMPY = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:  # pragma: no cover
    cv2 = None
    HAS_CV2 = False

from app.modules.plate_ocr import plate_text as pt

# ---------------------------------------------------------------------------
# تنظیمات موتور
# ---------------------------------------------------------------------------
WARP_W, WARP_H = 440, 110          # اندازه استاندارد پلاکِ راست‌شده
DET_CONF = 0.35
BOX_EXPAND = 0.08
# ۰٫۱۲ — اندازه‌گیری واقعی (اکتبر ۲۰۲۶): خوانش‌های درست عکس‌های خیابانی اغلب
# ۰٫۱۵-۰٫۴۵‌اند؛ دروازهٔ ۰٫۲۰ آن‌ها را پیش از اسمبلر حذف می‌کرد → «صفر کاندیدا»
MIN_CANDIDATE_CONF = 0.12
MAX_CANDIDATES = 8

PLATE_COLORS_FA = {
    "white": "سفید (شخصی)",
    "yellow": "زرد (عمومی/تاکسی)",
    "green": "سبز (مخصوص)",
    "red": "قرمز (موقت/عبوری)",
    "blue": "آبی (دیپلمات/تشریفات)",
    "unknown": "نامشخص",
}
PLATE_COLOR_RANGES = {
    "white":  ((0, 0, 180), (180, 40, 255)),
    "yellow": ((15, 80, 120), (35, 255, 255)),
    "green":  ((40, 60, 80), (85, 255, 255)),
    "red":    ((0, 100, 80), (10, 255, 255)),
    "blue":   ((90, 80, 60), (130, 255, 255)),
}


def capabilities(models_dir: str = "models") -> dict:
    """بررسی ارزان قابلیت‌ها — بدون لود کردن مدل‌ها."""
    import importlib.util
    import os

    def has(mod: str) -> bool:
        try:
            return importlib.util.find_spec(mod) is not None
        except Exception:
            return False

    yolo_w = os.path.join(models_dir, "plate_det_best.pt")
    pose_w = os.path.join(models_dir, "plate_pose_best.pt")
    crnn_w = os.path.join(models_dir, "crnn_best.pt")
    return {
        "numpy": HAS_NUMPY,
        "opencv": HAS_CV2,
        "easyocr": has("easyocr"),
        "torch": has("torch"),
        "ultralytics": has("ultralytics"),
        "yolo_weights": os.path.exists(yolo_w),
        "pose_weights": os.path.exists(pose_w),
        "crnn_weights": os.path.exists(crnn_w),
        "yolo_weights_path": yolo_w,
        "crnn_weights_path": crnn_w,
    }


# ---------------------------------------------------------------------------
# پیش‌پردازش تصویر
# ---------------------------------------------------------------------------
def enhance(img: "np.ndarray") -> "np.ndarray":
    """CLAHE روی کانال L + فیلتر دوجانبه (حذف نویز با حفظ لبه‌ها)."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(2.0, (8, 8)).apply(l)
    return cv2.bilateralFilter(cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR), 5, 40, 40)


def _order4(pts: "np.ndarray") -> "np.ndarray":
    pts = pts.reshape(4, 2).astype(np.float32)
    c = pts.mean(0)
    ang = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    pts = pts[np.argsort(ang)]
    k = int(np.argmin(pts.sum(1)))
    return np.roll(pts, -k, axis=0)


def _corners_canny(crop):
    gray = cv2.GaussianBlur(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(gray, 50, 150), np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape
    best, best_a = None, 0.4 * h * w
    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw * ch < best_a:
            continue
        ap = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(ap) == 4:
            best, best_a = ap.reshape(4, 2), cw * ch
    return best


def _corners_adaptive(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 21, 8)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    biggest = max(cnts, key=cv2.contourArea)
    ap = cv2.approxPolyDP(biggest, 0.03 * cv2.arcLength(biggest, True), True)
    return ap.reshape(4, 2).astype(np.float32) if len(ap) == 4 else None


def find_corners(crop):
    """گوشه‌یاب چند-استراتژی؛ در بدترین حالت گوشه‌های خود برش."""
    h, w = crop.shape[:2]
    for fn in (_corners_canny, _corners_adaptive):
        try:
            pts = fn(crop)
            if pts is not None and len(pts) == 4:
                return _order4(pts)
        except Exception:
            pass
    inset = 2
    return np.array([[inset, inset], [w - 1 - inset, inset],
                     [w - 1 - inset, h - 1 - inset], [inset, h - 1 - inset]], np.float32)


def warp_plate(crop) -> "np.ndarray":
    dst = np.float32([[0, 0], [WARP_W - 1, 0], [WARP_W - 1, WARP_H - 1], [0, WARP_H - 1]])
    try:
        M = cv2.getPerspectiveTransform(find_corners(crop), dst)
        return cv2.warpPerspective(crop, M, (WARP_W, WARP_H))
    except Exception:
        return cv2.resize(crop, (WARP_W, WARP_H))


def _upscale_to(img, target_h: int) -> "np.ndarray":
    if img.shape[0] >= target_h:
        return img
    f = max(2, int(np.ceil(target_h / img.shape[0])))
    return cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)


def _fit_ocr_size(img, target_h: int = 110, max_h: int = 150,
                  max_w: int = 1200) -> "np.ndarray":
    """الحاقیه §۳ — نرمال‌سازی اندازهٔ برش برای OCR.

    برش کوچک → بزرگ‌نمایی (مثل قبل). برش بزرگ (پلاک نزدیک در عکس موبایل/دوربین
    رزولوشن‌بالا) → کوچک‌سازی به ارتفاع ≤ ۱۵۰px: EasyOCR روی برش‌های بزرگ
    هم چند ثانیه کند است و هم پرنویز (اندازه‌گیری واقعی: برش ۳۱۰px → ~۹ ثانیه
    با خوانش آشفته؛ همان برش در ۱۴۰px → سریع‌تر و تمیزتر)."""
    h, w = img.shape[:2]
    if h < target_h:
        f = max(2, int(np.ceil(target_h / h)))
        return cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    if h > max_h or w > max_w:
        f = min(max_h / float(h), max_w / float(w))
        return cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return img


def expand_box(box, f: float = BOX_EXPAND):
    x1, y1, x2, y2 = [int(v) for v in box]
    w, h = x2 - x1, y2 - y1
    return (max(0, x1 - int(w * f)), max(0, y1 - int(h * f)), x2 + int(w * f), y2 + int(h * f))


def detect_plate_color(plate_bgr) -> tuple[str, float]:
    """تشخیص رنگ زمینه پلاک از روی HSV (ناحیه مرکزی)."""
    if plate_bgr is None or plate_bgr.size == 0:
        return "unknown", 0.0
    hsv = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2HSV)
    h, w = hsv.shape[:2]
    roi = hsv[int(0.15 * h):int(0.85 * h), int(0.05 * w):int(0.95 * w)]
    scores = {}
    for name, (lo, hi) in PLATE_COLOR_RANGES.items():
        scores[name] = float(cv2.inRange(roi, np.array(lo), np.array(hi)).mean()) / 255.0
    best, s = max(scores.items(), key=lambda kv: kv[1])
    return (best if s > 0.15 else "unknown"), round(s, 3)


# ---------------------------------------------------------------------------
# تشخیص کلاسیک (بدون YOLO)
# ---------------------------------------------------------------------------
def _classical_detect(bgr) -> list[tuple]:
    """یافتن نواحی شبیه پلاک با ماسک رنگ + کانتور + فیلتر نسبت ابعاد.

    پلاک ایران: مستطیل عریض (نسبت ~۴.۵) با زمینه سفید/زرد و قاب تیره.
    """
    H, W = bgr.shape[:2]
    scale = 1.0
    if max(H, W) < 640:                       # عکس کوچک → بزرگ‌نمایی برای کانتور بهتر
        scale = 640.0 / max(H, W)
        bgr = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    h, w = bgr.shape[:2]

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    masks = [
        cv2.inRange(hsv, np.array((0, 0, 150)), np.array((180, 70, 255))),   # سفید
        cv2.inRange(hsv, np.array((15, 80, 120)), np.array((35, 255, 255))),  # زرد
        cv2.inRange(hsv, np.array((95, 60, 60)), np.array((135, 255, 255))),  # آبی (دیپلمات/تشریفات)
    ]
    boxes: list[tuple] = []
    # نکته: حداکثر ارتفاع ۰٫۹۲ — در عکس‌های نزدیک (دست/موبایل) پلاک ممکن است
    # بیشترِ کادر را بگیرد؛ سقف ۰٫۳۵ باعث می‌شد تشخیص شکست بخورد و مسیر
    # گرانِ OCR کل-تصویر (۱۰ تا ۴۰ ثانیه روی CPU) اجرا شود.
    min_h, max_h = int(h * 0.030), int(h * 0.92)
    for m in masks:
        closed = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                                  cv2.getStructuringElement(cv2.MORPH_RECT, (21, 5)))
        cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            x, y, cw, ch = cv2.boundingRect(c)
            if not (min_h <= ch <= max_h) or cw < ch * 1.5:
                continue
            # نسبت ۱٫۸ تا ۸٫۵ — در نمای نزدیک پلاک ممکن است از کادر بیرون بزند
            # و نسبت به‌مراتب کمتر از ۴٫۵ استاندارد شود
            aspect = cw / float(ch)
            if not (1.8 <= aspect <= 8.5):
                continue
            area_ratio = cw * ch / float(w * h)
            if area_ratio < 0.002:
                continue
            solidity = cw * ch / max(cv2.contourArea(c), 1.0)
            if solidity > 1.6:
                continue
            boxes.append((x / scale, y / scale, (x + cw) / scale, (y + ch) / scale))

    # حذف جعبه‌های هم‌پوشان (سقف ۴ — تشخیص‌گر گرادیانی مکملِ این تابع است)
    boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    keep: list[tuple] = []
    for b in boxes:
        if all(_iou(b, k) < 0.30 for k in keep):
            keep.append(b)
    return keep[:4]


def _text_detect(bgr) -> list[tuple]:
    """تشخیص با گروه‌بندی نویسه + قاب پلاک — مکمل ماسک رنگ.

    دو شکست واقعی ماسک رنگ:
      * پلاک سفید روی بدنهٔ سفید — ماسک سفید کل بدنه را می‌گیرد؛
      * پلاک کوچک در صحنه — پس از بستن مورفولوژی به بدنه می‌چسبد.
    دو سیگنال مستقل:
      ۱) قاب پلاک: کانتور توخالی (حلقهٔ تیره) با داخل روشن و نسبت عریض؛
      ۲) نویسه‌ها: بلاب‌های کوچک تیره که در یک خط افقی گروه می‌شوند
         (با رشد لنگردار برای پلاک کج/ناقص).
    خروجی: جعبه‌های کاندید پلاک (x1, y1, x2, y2).
    """
    if not HAS_CV2 or bgr is None or bgr.size == 0:
        return []
    H, W = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 25, 11)
    cnts, hier = cv2.findContours(th, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return []
    hier = hier[0]

    # ---------- ۱) قاب پلاک: کانتور دارای سوراخ بزرگ با داخل روشن ----------
    frame_boxes: list[tuple] = []
    group_boxes: list[tuple] = []
    for i, c in enumerate(cnts):
        child = hier[i][2]
        if child == -1:
            continue
        # قاب پلاک چند سوراخ دارد (زمینهٔ داخلی + نویسه‌های چسبیده) —
        # بیشینهٔ مساحت سوراخ‌ها ملاک است، نه فقط اولین فرزند
        hole_max = 0.0
        ch_it = child
        while ch_it != -1:
            hole_max = max(hole_max, cv2.contourArea(cnts[ch_it]))
            ch_it = hier[ch_it][0]
        x, y, cw, ch = cv2.boundingRect(c)
        if not (10 <= ch <= H * 0.60):
            continue
        ar = cw / float(ch)
        if not (2.2 <= ar <= 9.0):
            continue
        if cw * ch < 0.0015 * W * H:
            continue
        if hole_max < 0.30 * cw * ch:
            continue
        inner = gray[int(y + 0.25 * ch):int(y + 0.75 * ch),
                     int(x + 0.15 * cw):int(x + 0.85 * cw)]
        if inner.size == 0 or float(inner.mean()) < 130:
            continue
        frame_boxes.append((x, y, x + cw, y + ch))

    # ---------- ۲) نویسه‌های کاندید ----------
    chars: list[tuple] = []
    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        if not (5 <= ch <= H * 0.55):
            continue
        ar = cw / float(ch)
        if not (0.12 <= ar <= 1.45):
            continue
        if cv2.contourArea(c) < 0.18 * cw * ch:
            continue
        pad = 3
        roi = gray[max(0, y - pad):min(H, y + ch + pad),
                   max(0, x - pad):min(W, x + cw + pad)]
        if roi.size == 0 or float(roi.mean()) < 100:
            continue
        chars.append((x, y, x + cw, y + ch))

    # الحاقیه §۳ — سقف نویسه‌ها: بافت‌های پرنویز (آسفالت/برگ) هزاران بلاب
    # می‌سازند و گروه‌بندی خطی O(n²) را منفجر می‌کنند (اندازه‌گیری: ~۲۴ ثانیه
    # روی عکس ۱۲MP). بزرگ‌ترین‌ها نگه داشته می‌شوند — نویسه‌های پلاک همیشه از
    # کوچک‌ترین‌ها بزرگ‌ترند.
    if len(chars) > 2500:
        chars.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
        chars = chars[:2500]
    chars.sort(key=lambda b: (b[1], b[0]))
    used = [False] * len(chars)
    groups: list[list[int]] = []
    for i, s in enumerate(chars):
        if used[i]:
            continue
        group = [s]
        used[i] = True
        changed = True
        while changed:
            changed = False
            gx1 = min(g[0] for g in group); gx2 = max(g[2] for g in group)
            gy1 = min(g[1] for g in group); gy2 = max(g[3] for g in group)
            gh = max(1, gy2 - gy1)
            for j, t in enumerate(chars):
                if used[j]:
                    continue
                tx1, ty1, tx2, ty2 = t
                thh = ty2 - ty1
                if min(gy2, ty2) - max(gy1, ty1) < 0.30 * min(gh, thh):
                    continue          # هم‌ترازی عمودی
                if not (0.35 <= thh / float(gh) <= 2.8):
                    continue          # ارتفاع مشابه (پلاک کج)
                if max(tx1 - gx2, gx1 - tx2, -1) > 1.6 * max(gh, thh):
                    continue          # فاصلهٔ افقی منطقی
                group.append(t)
                used[j] = True
                changed = True
        if len(group) >= 4:
            groups.append([min(g[0] for g in group), min(g[1] for g in group),
                           max(g[2] for g in group), max(g[3] for g in group)])

    # ادغام گروه‌های هم‌خط (مثلاً گروه ارقام + گروه کد استان)
    merged = True
    while merged:
        merged = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i], groups[j]
                ah, bh = a[3] - a[1], b[3] - b[1]
                if min(a[3], b[3]) - max(a[1], b[1]) > 0.25 * min(ah, bh) and \
                        max(b[0] - a[2], a[0] - b[2], -1) < 2.0 * max(ah, bh):
                    groups[i] = [min(a[0], b[0]), min(a[1], b[1]),
                                 max(a[2], b[2]), max(a[3], b[3])]
                    groups.pop(j)
                    merged = True
                    break
            if merged:
                break

    # رشد لنگردار — نویسه‌های کج/کم‌کنتراستِ اطراف گروه هم جذب می‌شوند
    for _ in range(3):
        grown = False
        for gi, box in enumerate(groups):
            x1, y1, x2, y2 = box
            gh = max(1, y2 - y1)
            cx1, cx2 = x1 - 1.3 * gh, x2 + 1.3 * gh
            cy1, cy2 = y1 - 0.8 * gh, y2 + 0.8 * gh
            for t in chars:
                tcx, tcy = (t[0] + t[2]) / 2.0, (t[1] + t[3]) / 2.0
                if cx1 <= tcx <= cx2 and cy1 <= tcy <= cy2:
                    nb = [min(x1, t[0]), min(y1, t[1]), max(x2, t[2]), max(y2, t[3])]
                    if nb != box:
                        groups[gi] = nb
                        grown = True
        if not grown:
            break

    for gx1, gy1, gx2, gy2 in groups:
        gw, gh = gx2 - gx1, gy2 - gy1
        if not (2.2 <= gw / float(max(1, gh)) <= 9.0):
            continue
        if gh < 9:
            continue
        if float(gray[gy1:gy2, gx1:gx2].mean()) < 110:
            continue
        group_boxes.append((gx1, gy1, gx2, gy2))

    # حذف هم‌پوشان — قاب پلاک دقیق‌ترین جعبه است و اولویت دارد؛ گروه نویسه
    # فقط اگر با قاب هم‌پوشان نباشد اضافه می‌شود (در غیر این صورت ناقص است)
    uniq: list[tuple] = []
    for b in sorted(frame_boxes, key=_detect_priority, reverse=True):
        if all(_iou(b, u) < 0.35 for u in uniq):
            uniq.append(b)
    for b in sorted(group_boxes, key=_detect_priority, reverse=True):
        if all(_iou(b, u) < 0.30 for u in uniq):
            uniq.append(b)
    return uniq[:5]


def _detect_priority(box) -> tuple:
    """کلید اولویت OCR: شباهت نسبت ابعاد به پلاک ایران (۴٫۷۳) + مساحت.

    جعبهٔ درست معمولاً نسبت نزدیک ۴٫۷ دارد؛ بدنهٔ ماشین/پنجره/دیوار نسبت
    متفاوتی دارند. با این ترتیب، پلاک واقعی زودتر OCR می‌شود و سقف زمانی
    پیش از رسیدن به باکس‌های زباله تمام نمی‌شود.
    """
    x1, y1, x2, y2 = box
    w, h = max(1, x2 - x1), max(1, y2 - y1)
    aspect = w / float(h)
    a_score = max(0.0, 1.0 - abs(aspect - 4.73) / 4.73)
    return (a_score, w * h)


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter <= 0:
        return 0.0
    sa = (a[2] - a[0]) * (a[3] - a[1])
    sb = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (sa + sb - inter)


# ---------------------------------------------------------------------------
# موتور اصلی
# ---------------------------------------------------------------------------
@dataclass
class _Candidate:
    text: str
    conf: float
    method: str
    valid: bool = False
    box: tuple | None = None
    crop_b64: str | None = None
    score: float = field(default=0.0)


class PlateReader:
    """سینگلتون سرویس پلاک‌خوان — مدل‌ها lazy و با قفل لود می‌شوند."""

    def __init__(self, models_dir: str = "models"):
        self.models_dir = models_dir
        self._easy = None
        self._easy_err: str | None = None
        self._crnn = None
        self._yolo = None
        self._yolo_err: str | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------ لود تنبل بک‌اندها
    def _get_easy(self):
        with self._lock:
            if self._easy is not None or self._easy_err:
                return self._easy
            try:
                from easyocr import Reader
                import torch
                self._easy = Reader(["fa", "en"], gpu=torch.cuda.is_available(), verbose=False)
            except Exception as exc:  # pragma: no cover
                self._easy_err = str(exc)
        return self._easy

    def _get_crnn(self):
        with self._lock:
            if self._crnn is not None or self._crnn is False:
                return self._crnn
            import os
            w = os.path.join(self.models_dir, "crnn_best.pt")
            if not os.path.exists(w):
                self._crnn = False
                return None
            try:
                import torch
                import torch.nn as nn

                class _SE(nn.Module):
                    def __init__(self, c, r=8):
                        super().__init__()
                        self.fc1 = nn.Conv2d(c, max(4, c // r), 1)
                        self.fc2 = nn.Conv2d(max(4, c // r), c, 1)

                    def forward(self, x):
                        s = x.mean((2, 3), keepdim=True)
                        s = torch.sigmoid(self.fc2(torch.relu(self.fc1(s))))
                        return x * s

                class _CRNN(nn.Module):
                    def __init__(self, num_classes, img_h=64):
                        super().__init__()

                        def cr(i, o, k=3, s=1, p=1, bn=False):
                            ls = [nn.Conv2d(i, o, k, s, p)]
                            if bn:
                                ls.append(nn.BatchNorm2d(o))
                            ls.append(nn.ReLU(inplace=True))
                            return nn.Sequential(*ls)

                        self.cnn = nn.Sequential(
                            cr(1, 64), nn.MaxPool2d(2, 2),
                            cr(64, 128), nn.MaxPool2d(2, 2),
                            cr(128, 256), cr(256, 256), nn.MaxPool2d((2, 1), (2, 1)),
                            cr(256, 512, bn=True), _SE(512),
                            cr(512, 512, bn=True), nn.MaxPool2d((2, 1), (2, 1)),
                            cr(512, 512, bn=True), _SE(512),
                            nn.AdaptiveAvgPool2d((1, None)),
                        )
                        self.rnn = nn.LSTM(512, 256, 2, bidirectional=True, batch_first=True)
                        self.dropout = nn.Dropout(0.1)
                        self.fc = nn.Linear(512, num_classes)

                    def forward(self, x):
                        c = self.cnn(x)
                        r, _ = self.rnn(c.squeeze(2).transpose(1, 2))
                        return self.fc(self.dropout(r)).log_softmax(2)

                ckpt = torch.load(w, map_location="cpu")
                chars = ckpt.get("chars") or pt.DIGITS + pt.LETTERS
                self._crnn_chars = chars
                self._crnn_c2i = {c: i + 1 for i, c in enumerate(chars)}
                model = _CRNN(ckpt.get("num_classes", len(chars) + 1), ckpt.get("img_h", 64))
                model.load_state_dict(ckpt["model"], strict=False)
                model.eval()
                self._crnn = model
            except Exception:
                self._crnn = False
        return self._crnn or None

    def _get_yolo(self):
        with self._lock:
            if self._yolo is not None or self._yolo_err:
                return self._yolo
            import os
            w = os.path.join(self.models_dir, "plate_det_best.pt")
            if not os.path.exists(w):
                self._yolo_err = "weights-missing"
                return None
            try:
                from ultralytics import YOLO
                self._yolo = YOLO(w)
            except Exception as exc:
                self._yolo_err = str(exc)
        return self._yolo

    # ------------------------------------------------ OCR کاندیداها
    def _ocr_crop(self, crop, **easy_kw) -> list[tuple[str, float, str]]:
        """همه کاندیداهای متنی یک برش پلاک — (متن، اطمینان، روش).

        easy_kw: تنظیمات اضافی readtext (مثل text_threshold/low_text برای
        واریانت CRAFT باز).
        """
        out: list[tuple[str, float, str]] = []
        model = self._get_crnn()
        if model is not None:
            try:
                import torch
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
                img = cv2.resize(gray, (320, 64))
                t = torch.from_numpy(img).float().div(255).unsqueeze(0).unsqueeze(0)
                with torch.no_grad():
                    logp = model(t)[0]
                pred = logp.argmax(1).cpu().numpy()
                idx2ch = {i + 1: c for i, c in enumerate(self._crnn_chars)}
                chars, prev, confs = [], 0, []
                for ti, p in enumerate(pred):
                    p = int(p)
                    if p != prev and p != 0:
                        chars.append(idx2ch.get(p, ""))
                        confs.append(float(np.exp(logp[ti, p])))
                    prev = p
                text = "".join(chars)
                conf = float(min(confs)) if confs else 0.0
                out.append((text, conf, "crnn"))
            except Exception:
                pass

        easy = self._get_easy()
        if easy is not None:
            try:
                with self._lock:
                    # canvas ۷۶۸ برای برشِ ≤۴۴۰×۱۱۰ کافی است — نصف زمان CRAFT
                    res = easy.readtext(crop, detail=1, paragraph=False,
                                        allowlist=pt.OCR_ALLOWLIST,
                                        workers=0, mag_ratio=1.0, canvas_size=768,
                                        **easy_kw)
                if res:
                    pieces = [(float(bb[0][0]), txt, float(c)) for bb, txt, c in res]
                    # حذف قطعات بلندِ بدون رقم — باقیمانده‌های متن صحنه/کلمه ایرانِ ناخوانا
                    # (پلاک همیشه رقم دارد؛ فقط قطعات کوتاه ۱-۲ نویسه‌ای حرف می‌توانند معتبر باشند)
                    pieces = [p for p in pieces
                              if p[2] >= MIN_CANDIDATE_CONF
                              and (any(ch.isdigit() for ch in p[1]) or len(p[1]) <= 2)]
                    if pieces:
                        # الحاقیه §۳ — اسمبلر ساخت‌یافته (مقید به قالب ایران):
                        # از قطعات (حتی پراکنده) همهٔ ترکیب‌های قالب‌معتبر ساخته
                        # می‌شود؛ این مسیر خوانش‌های چندقطعه‌ایِ واقعی را نجات
                        # می‌دهد (تأیید روی عکس واقعی گیت: قطعات «73» + «934340»
                        # → کاندیدای معتبر ۸ نویسه‌ای).
                        # فقط برای ≥۲ قطعه — تک‌قطعه مسیر _collect/repair را دارد
                        # و تکرارش رأی ساختگی می‌سازد (۵.jpeg: همان «22د111»
                        # هم از assemble و هم از enforce → رأی دوبرابر)
                        if len(pieces) >= 2:
                            try:
                                for assembled, sc in pt.assemble_from_pieces(pieces)[:3]:
                                    if sc >= MIN_CANDIDATE_CONF:
                                        out.append((assembled, min(0.99, sc), "easyocr-assemble"))
                            except Exception:
                                pass
                        # concat فقط با قطعات پراطمینان — قطعهٔ ضعیف («۱۸» به‌جای ۷۲)
                        # خوانش اصلی را مسموم می‌کند
                        strong = [p for p in pieces if p[2] >= 0.45]
                        use = strong if strong else pieces
                        rtl = "".join(t for _, t, _ in sorted(use, key=lambda p: -p[0]))
                        ltr = "".join(t for _, t, _ in sorted(use, key=lambda p: p[0]))
                        conf = max(p[2] for p in use)
                        out.append((rtl, conf, "easyocr"))
                        if ltr != rtl:
                            out.append((ltr, conf, "easyocr-ltr"))
                        # تک‌قطعه‌ها هم کاندیدای مستقل — قطعهٔ زباله («۴۸» پرچم) نباید
                        # به خوانش اصلی بچسبد؛ قطعهٔ «۱۳۸۸۱۱۱» تنها قابل‌ترمیم است
                        for _x, txt, c in pieces:
                            nt = pt.normalize(txt)
                            if 3 <= len(nt) <= 9:
                                out.append((nt, c, "easyocr-piece"))
            except Exception:
                pass
        return out

    # ------------------------------------------------ تشخیص
    def _detect(self, bgr) -> list[tuple]:
        """[(box, warp|None), ...] — YOLO اگر موجود، وگرنه کلاسیک + گرادیانی.

        ماسک رنگ و تراکم لبه مکمل‌اند: ماسک رنگ در نمای نزدیک خوب است،
        تراکم لبه پلاک سفید روی بدنهٔ سفید و پلاک کوچک را پیدا می‌کند.
        خروجی با اولویتِ شباهت نسبت ابعاد به ۴٫۷۳ مرتب می‌شود.
        """
        yolo = self._get_yolo()
        if yolo is not None:
            try:
                res = yolo(bgr, conf=DET_CONF, verbose=False)[0]
                if res.boxes is not None and len(res.boxes):
                    return [(tuple(b), None)
                            for b in res.boxes.xyxy.cpu().numpy().astype(int)]
            except Exception:
                pass
        boxes = _classical_detect(bgr)
        # الحاقیه §۳ — بودجهٔ هزینهٔ تشخیص: _text_detect روی تصاویر بزرگِ بافت‌دار
        # (آسفالت/سقف در عکس موبایل ۱۲MP) تا ~۲۴ ثانیه کش می‌آمد (اندازه‌گیری
        # واقعی). راه‌حل: اجرای همیشگی (برای پوشش سفید-روی-سفید — رگرسیون car2/car3)
        # اما روی نسخهٔ کوچک‌شدهٔ ≤۱۴۰۰px + سقف تعداد نویسه‌ها در گروه‌بندی.
        H, W = bgr.shape[:2]
        tsc = min(1.0, 1400.0 / max(H, W))
        if tsc < 1.0:
            probe = cv2.resize(bgr, None, fx=tsc, fy=tsc, interpolation=cv2.INTER_AREA)
        else:
            probe = bgr
        for tb in _text_detect(probe):
            tb2 = (tb[0] / tsc, tb[1] / tsc, tb[2] / tsc, tb[3] / tsc)
            if all(_iou(tb2, b) < 0.35 for b in boxes):
                boxes.append(tb2)
        # الحاقیه §۳ — جریمهٔ جعبهٔ لبه‌چسب: خط سقف/افق و کادر تصویر که از گوشه
        # شروع می‌شوند معمولاً پس‌زمینه‌اند اما نسبت ابعادشان شبیه پلاک است و
        # اولویت می‌گرفتند، بودجهٔ زمانی OCR را می‌سوزاندند و پلاک واقعی از دست
        # می‌رفت (تأیید روی عکس واقعی گیت). فقط برشِ گوشه‌ای/نوار کامل جریمه می‌شود.
        H, W = bgr.shape[:2]

        def _prio(b):
            a_score, area = _detect_priority(b)
            x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
            # جریمهٔ دقیق‌تر: فقط (الف) جعبه‌ای که دقیقاً از گوشهٔ بالای تصویر
            # شروع می‌شود (خط سقف/افق — مورد واقعی گیت) و (ب) نوار تمام‌عرض/
            # تمام‌ارتفاع. پلاکِ کلوزآپی که به لبهٔ راست/پایین می‌چسبد جریمه
            # نمی‌شود (رگرسیون car1).
            if x1 <= 2 and y1 <= 2:
                a_score -= 0.5
            elif x1 <= 2 and x2 >= W - 3:
                a_score -= 0.3
            elif y1 <= 2 and y2 >= H - 3:
                a_score -= 0.3
            return (a_score, area)

        boxes.sort(key=_prio, reverse=True)
        return [(b, None) for b in boxes[:5]]

    # ------------------------------------------------ برش پلاک
    def _plate_crop(self, bgr, box) -> "np.ndarray | None":
        """برش از تصویر خام + enhance روی خود برش + راست‌کردن (warp).

        ترتیب مهم است: CLAHE روی کل تصویر تقطیع متفاوتی دارد؛ enhance باید
        روی برش انجام شود تا با شرایط آزمایش‌شده یکی باشد."""
        x1, y1, x2, y2 = expand_box(box)
        H, W = bgr.shape[:2]
        crop = bgr[max(0, y1):min(H, y2), max(0, x1):min(W, x2)]
        if crop.size == 0 or crop.shape[0] < 10 or crop.shape[1] < 30:
            return None
        return _fit_ocr_size(warp_plate(_upscale_to(enhance(crop), 96)), 110)

    def _plain_crop(self, bgr, box, *, margin: float = 0.005,
                    target_h: int = 140, enhance_img: bool = True) -> "np.ndarray | None":
        """برش ساده بدون وارپ — حاشیهٔ تقریباً صفر؛ جعبه‌های تشخیص خودشان تنگ‌اند
        و حاشیهٔ اضافی نوار پرچم/بدنه را وارد OCR می‌کند و خوانش را خراب
        (آزمایش واقعی: حاشیهٔ ۸٪ خوانش ۰٫۵۶ را به هیچ رساند).

        enhance_img=False — برش خام بدون CLAHE/bilateral: اندازه‌گیری ۴.jpg
        نشان داد enhance روی برش‌های کوچکِ کم‌سایه ارقام را کامل حذف می‌کند
        (خام «۱۱ق۱۱» با ۰٫۷۲؛ همان برش با enhance فقط «ق» پس از ۷٫۸ ثانیه).
        """
        x1, y1, x2, y2 = [int(v) for v in box]
        w, h = x2 - x1, y2 - y1
        H, W = bgr.shape[:2]
        x1, y1 = max(0, x1 - int(w * margin)), max(0, y1 - int(h * margin))
        x2, y2 = min(W, x2 + int(w * margin)), min(H, y2 + int(h * margin))
        crop = bgr[max(0, y1):min(H, y2), max(0, x1):min(W, x2)]
        if crop.size == 0 or crop.shape[0] < 10 or crop.shape[1] < 30:
            return None
        return _fit_ocr_size(enhance(crop) if enhance_img else crop, target_h)

    # ------------------------------------------------ برش حاشیه‌دار آزاد
    def _margin_crop(self, bgr, box, *, fx: float = 0.45, fy: float = 0.60,
                     target_h: int = 130) -> "np.ndarray | None":
        """برش با حاشیهٔ سخاوتمند + بزرگ‌نمایی — برای جعبه‌های یافتهٔ کل-تصویر.

        جعبهٔ متن EasyOCR تنگ است (فقط نویسه‌ها)؛ قاب پلاک حاشیهٔ بیشتری
        می‌خواهد تا گوشه‌یاب و OCR بهتر کار کنند.
        """
        x1, y1, x2, y2 = [int(v) for v in box]
        w, h = x2 - x1, y2 - y1
        H, W = bgr.shape[:2]
        x1, y1 = max(0, x1 - int(w * fx)), max(0, y1 - int(h * fy))
        x2, y2 = min(W, x2 + int(w * fx)), min(H, y2 + int(h * fy))
        crop = bgr[max(0, y1):y2, max(0, x1):x2]
        if crop.size == 0 or crop.shape[0] < 8 or crop.shape[1] < 24:
            return None
        return _fit_ocr_size(enhance(crop), target_h)

    @staticmethod
    def _binarize(crop) -> "np.ndarray | None":
        """واریانت باینریِ برش پلاک — برای عکس‌های کم‌کنتراست/کدر.

        آستانهٔ تطبیقی روی خاکستریِ بزرگ‌نمایی‌شده؛ خروجی ۳ کاناله برای EasyOCR.
        """
        if not HAS_CV2 or crop is None or crop.size == 0:
            return None
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        gray = _upscale_to(gray, 140)
        th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 35, 12)
        return cv2.cvtColor(th, cv2.COLOR_GRAY2BGR)

    @staticmethod
    def _sharpen(crop) -> "np.ndarray | None":
        """واریانت تیزشده (unsharp ملایم) — عکس موبایل کمی نرم است؛ لبهٔ ارقام
        ریز برمی‌گردد و CRAFT با آستانهٔ باز گروه‌های جاافتاده را می‌گیرد."""
        if not HAS_CV2 or crop is None or crop.size == 0:
            return None
        blur = cv2.GaussianBlur(crop, (0, 0), 2.0)
        return cv2.addWeighted(crop, 1.6, blur, -0.6, 0)

    @staticmethod
    def _seg_main(crop) -> "np.ndarray | None":
        """بخش اصلی پلاک — حذف نوار پرچم، کادر و کادر کد استان.

        قالب پلاک ایران: [نوار پرچم ~۸٪][۲رقم+حرف+۳رقم ~۷۲٪][کد استان ~۱۹٪].
        خوانش جداگانهٔ بخش اصلی آلودگی نوار/کادر را حذف می‌کند (اندازه‌گیری
        واقعی ۵.jpeg: کل برش «٢٢٥١١» نامعتبر؛ بخشِ اصلی «٢٢٥١١١» با اطمینان
        ۰٫۷۴ → پس از نگاشت ۵→د همان «۲۲ د ۱۱۱» درست).
        """
        if not HAS_CV2 or crop is None or crop.size == 0:
            return None
        h, w = crop.shape[:2]
        if w < 60 or h < 24:
            return None
        return crop[int(0.12 * h):int(0.90 * h), int(0.085 * w):int(0.805 * w)]

    # ------------------------------------------------ یافتن متن در کل تصویر
    def _fullimage_locate(self, bgr_full) -> list[tuple]:
        """جعبه‌های متنیِ شبیه پلاک روی کل تصویر — بدون OCR دقیق.

        OCR مستقیمِ کل تصویر روی متن ریز جواب غلط می‌دهد (نمونهٔ واقعی:
        «۱۴ب۵۹۱» خوانده شد «۸۴۰ب۵۶۹»). به‌جای آن:
          ۱) CRAFT جعبه‌های متن را پیدا می‌کند (حتی کم‌اطمینان)؛
          ۲) جعبه‌های عریض (نسبت ≥۲) شبیه پلاک نگه داشته می‌شوند؛
          ۳) caller هر جعبه را با کیفیت کامل برش و بزرگ‌نمایی و دوباره OCR می‌کند.
        """
        easy = self._get_easy()
        if easy is None:
            return []
        H, W = bgr_full.shape[:2]
        fi = bgr_full
        if max(H, W) > 1280:
            f = 1280.0 / max(H, W)
            fi = cv2.resize(fi, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        try:
            with self._lock:
                # بدون allowlist — هدف «مکان‌یابی» است نه خواندن؛ آستانه‌های پایین‌تر
                # تا متن ریزِ پلاک هم جعبه بگیرد
                res = easy.readtext(fi, detail=1, paragraph=False, workers=0,
                                    text_threshold=0.5, low_text=0.3,
                                    mag_ratio=1.0, canvas_size=1152)
        except Exception:
            return []
        s = W / float(fi.shape[1])
        boxes: list[tuple] = []
        for bb, _txt, _conf in res:
            xs = [p[0] for p in bb]
            ys = [p[1] for p in bb]
            x1, y1, x2, y2 = min(xs) * s, min(ys) * s, max(xs) * s, max(ys) * s
            w_, h_ = x2 - x1, y2 - y1
            if h_ < 8 or w_ < 2.0 * h_ or w_ > 9.5 * h_:
                continue
            if w_ * h_ < 0.0008 * W * H:
                continue
            boxes.append((int(x1), int(y1), int(x2), int(y2)))
        # حذف هم‌پوشان + اولویت نسبت ابعاد
        uniq: list[tuple] = []
        for b in sorted(boxes, key=_detect_priority, reverse=True):
            if all(_iou(b, u) < 0.30 for u in uniq):
                uniq.append(b)
        return uniq[:4]

    # ------------------------------------------------ ساخت کاندیداها
    def _collect(self, cands: list[_Candidate], text: str, conf: float,
                 method: str, box) -> bool:
        """افزودن کاندیدای خام + ترمیم‌ها؛ خروجی: آیا کاندیدای معتبر ساخته شد؟"""
        norm, valid = pt.validate(text)
        cands.append(_Candidate(norm, conf, method, valid, box, None))
        if valid:
            return True
        made_valid = False
        emitted: set[str] = set()
        if len(norm) in (6, 8):
            fixed = pt.enforce_format(norm)
            if fixed != norm and fixed not in emitted and pt.validate(fixed)[1]:
                emitted.add(fixed)
                cands.append(_Candidate(fixed, conf * 0.95, f"{method}+enforce",
                                        True, box, None))
                made_valid = True
        for fixed, mul in pt.repair_candidates(norm):
            if fixed in emitted:
                continue
            emitted.add(fixed)
            cands.append(_Candidate(fixed, conf * mul, f"{method}+repair",
                                    True, box, None))
            made_valid = True
        return made_valid

    # ------------------------------------------------ نقطه ورود
    def read_image(self, bgr, *, min_conf: float = 0.25,
                   want_annotated: bool = True,
                   fast_mode: bool = True) -> dict:
        """تحلیل کامل یک تصویر → دیکشنری نتیجه (JSON-serializable).

        fast_mode=True: اگر از برش‌های پلاک کاندیدا ساخته شد (حتی نامعتبر
        ولی قابل‌ترمیم)، OCR گرانِ کل-تصویر اجرا نمی‌شود — سرعت ~۱۰ برابر.
        """
        t0 = time.perf_counter()
        caps = capabilities(self.models_dir)

        # محدود کردن اندازه برای کنترل زمان CPU
        H, W = bgr.shape[:2]
        if max(H, W) > 2600:
            f = 2600.0 / max(H, W)
            bgr = cv2.resize(bgr, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)

        cands: list[_Candidate] = []

        t1 = time.perf_counter()
        dets = self._detect(bgr)          # تشخیص روی تصویر خام — مقاوم‌تر
        detect_ms = round((time.perf_counter() - t1) * 1000)

        method_prefix = "yolo" if self._get_yolo() is not None else "classical"
        ocr_crops_ms = 0.0
        valid_count = 0
        for i, (box, _warp) in enumerate(dets[:3]):
            # سقف زمانی: هر باکس ~۱ تا ۳ ثانیه OCR می‌برد — بعد از ۲ کاندیدای
            # معتبر، یا ۶ ثانیه پس از اولین کاندیدا، یا ۱۲ ثانیه مطلق، باکس‌های
            # باقی‌مانده بی‌ارزش‌تر از هزینه‌اند
            _el = time.perf_counter() - t0
            if valid_count >= 2 or (valid_count >= 1 and _el > 6.0) or _el > 12.0:
                break

            def _feed(ocrs: list, tag: str) -> bool:
                # دروازهٔ قطعات فقط ثابتِ موتور است — اسلایدر min_conf کاربر
                # سرانجام در انتخاب best اعمال می‌شود؛ این‌جا عبور قطعات ضعیف
                # لازم است تا اسمبلر/ترمیم بتواند کاندیدای قالب‌معتبر بسازد.
                # حذف تکرارِ متن در خروجی یک readtext («٢٢٥١١١» + کپی piece آن
                # «225111»): تکرارِ رأی مصنوعی می‌سازد نه تأیید مستقل
                got = False
                best_by_text: dict[str, tuple] = {}
                for text, conf, ocr_method in ocrs:
                    if conf < MIN_CANDIDATE_CONF:
                        continue
                    norm_key = pt.normalize(text)
                    cur = best_by_text.get(norm_key)
                    if cur is None or conf > cur[1]:
                        best_by_text[norm_key] = (text, conf, ocr_method)
                for text, conf, ocr_method in best_by_text.values():
                    if self._collect(cands, text, conf,
                                     f"{method_prefix}+{ocr_method}+{tag}", box):
                        got = True
                return got

            # مسیر ۱: برش سادهٔ تنگ — «خام» اول (اندازه‌گیری ۴.jpg: enhance روی
            # برش کوچک ارقام را کامل حذف می‌کند) و بعد enhance‌شده؛ برای هرکدام
            # خوانش کل برش + بخش اصلی (بدون نوار پرچم/کادر/کد استان — ۵.jpeg)
            crop_raw = self._plain_crop(bgr, box, enhance_img=False)
            crop_enh = self._plain_crop(bgr, box)
            variants: list[tuple] = []
            for c_img, c_tag in (
                    (crop_raw, "crop"),
                    (self._seg_main(crop_raw) if crop_raw is not None else None, "seg"),
                    (crop_enh, "crop-enh"),
                    (self._seg_main(crop_enh) if crop_enh is not None else None, "seg-enh")):
                if c_img is not None:
                    variants.append((c_img, c_tag))
            hit_strong = False
            got_any = False
            for v_img, v_tag in variants:
                if cands and (time.perf_counter() - t0) > 14.0:
                    break
                t2 = time.perf_counter()
                ocrs_v = self._ocr_crop(v_img)
                ocr_crops_ms += time.perf_counter() - t2
                if _feed(ocrs_v, v_tag):
                    got_any = True
                    # خروج زودهنگام فقط با خوانشِ قوی — کاندیدای ضعیفِ ترمیمی
                    # نباید واریانت دقیق‌تر بعدی را قفل کند (۵.jpeg: ترمیمِ ضعیف
                    # seg خام در برابر «۲۲ د ۱۱۱» دقیق از seg-enhanced)
                    if any(c.valid and c.conf >= 0.55 for c in cands):
                        hit_strong = True
                        break
            if hit_strong:
                valid_count += 1
                continue
            if crop_raw is None:
                continue

            # مسیر ۲: بزرگ‌نمایی ۲ برابری — خوانش‌های ریز/بلوری را نجات می‌دهد
            # (اندازه‌گیری واقعی روی عکس گیت: ۰٫۵۶ → ۰٫۹۹ روی همان برش)
            if crop_raw.shape[0] < 260:
                crop2x = cv2.resize(crop_raw, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                t2 = time.perf_counter()
                ocrs2x = self._ocr_crop(crop2x)
                ocr_crops_ms += time.perf_counter() - t2
                if _feed(ocrs2x, "crop2x"):
                    got_any = True
                    if any(c.valid and c.conf >= 0.55 for c in cands):
                        valid_count += 1
                        continue

            # مسیر ۳: تیزشده + آستانهٔ باز CRAFT — ارقام ریزِ حذف‌شده برمی‌گردند
            # (۴.jpg: خوانش پایه یک گروه رقم را کامل جا انداخته بود). جایگزین
            # واریانت باینریِ کم‌اثر
            sh = self._sharpen(crop_raw)
            if sh is not None:
                t2 = time.perf_counter()
                ocrs_sh = self._ocr_crop(sh, text_threshold=0.4, low_text=0.25)
                ocr_crops_ms += time.perf_counter() - t2
                if _feed(ocrs_sh, "sharpen"):
                    got_any = True
                    if any(c.valid and c.conf >= 0.55 for c in cands):
                        valid_count += 1
                        continue

            # مسیر ۴: وارپ (راست‌کردن پرسپکتیو) — آخرین اولویت چون گوشه‌یاب در
            # نمای نزدیک/کج اغلب خطا می‌رود و زمانش با برش ساده برابر است
            crop = self._plate_crop(bgr, box)
            if crop is None:
                continue
            t2 = time.perf_counter()
            ocrs = self._ocr_crop(crop)
            ocr_crops_ms += time.perf_counter() - t2
            if _feed(ocrs, "warp"):
                got_any = True
            if got_any:
                valid_count += 1

        # مسیر جایگزین: مکان‌یابی متن روی کل تصویر + OCR متمرکزِ برش‌ها —
        # فقط وقتی از برش‌های تشخیص هیچ کاندیدایی نداریم (در fast_mode حتی
        # با کاندیدای نامعتبرِ قابل‌ترمیم هم رد می‌شود)
        fullimage_ms = 0.0
        fullimage_skipped: str | None = None
        if any(c.valid for c in cands):
            fullimage_skipped = "کاندیدای معتبر از برش پلاک یافت شد"
        elif fast_mode and any(len(c.text) >= 6 for c in cands):
            # فقط قطعات با طول نزدیک به پلاک (۶+) قابل‌ترمیم‌اند؛ تکه‌تکه‌های
            # کوتاه («۱س»، «۸۷») ارزش ترمیم ندارند و نباید جلوی مکان‌یابی را بگیرند
            fullimage_skipped = "fast-mode: کاندیدای قابل‌ترمیم از برش وجود دارد"
        elif (time.perf_counter() - t0) > 20.0:
            fullimage_skipped = "time-budget: پردازش برش‌ها بیش از ۲۰ ثانیه"
        else:
            t3 = time.perf_counter()
            locate_boxes = self._fullimage_locate(bgr)
            located_any = False
            for li, lb in enumerate(locate_boxes[:3]):
                lcrop = self._margin_crop(bgr, lb)
                if lcrop is None:
                    continue
                lvariants = [lcrop]
                # واریانت ۲x فقط برای جعبهٔ نخست — هر جعبه اضافه ~۱ تا ۲ ثانیه
                if li == 0 and lcrop.shape[0] < 260:
                    lvariants.append(cv2.resize(lcrop, None, fx=2, fy=2,
                                                interpolation=cv2.INTER_CUBIC))
                for lv in lvariants:
                    for text, conf, m in self._ocr_crop(lv):
                        if conf < MIN_CANDIDATE_CONF:
                            continue
                        if self._collect(cands, text, conf, f"locate+{m}", lb):
                            located_any = True
            if not located_any and not locate_boxes:
                # آخرین لنگر (رفتار قدیمی): OCR مستقیم کل تصویر — دقت پایین‌تر
                fi = bgr
                H2, W2 = fi.shape[:2]
                if max(H2, W2) > 1152:
                    f2 = 1152.0 / max(H2, W2)
                    fi = cv2.resize(fi, None, fx=f2, fy=f2, interpolation=cv2.INTER_AREA)
                for text, conf, m in self._ocr_crop(fi):
                    if conf < MIN_CANDIDATE_CONF:
                        continue
                    self._collect(cands, text, conf, f"fullimage+{m}", None)
            fullimage_ms = time.perf_counter() - t3

        # حذف تکراری + رأی‌شماری + امتیازدهی — تکرار یک متن در واریانت‌های
        # مختلف OCR نشانهٔ درستی است و امتیازش جمع می‌شود (تجمیع چند-خواننده)
        dedup: dict[str, _Candidate] = {}
        for c in cands:
            if not c.text or len(c.text) < 5 or len(c.text) > 9:
                continue    # پلاک ایران ۶/۸ نویسه است؛ خارج از بازه نزدیک = نویز صحنه
            c.score = (2.0 if c.valid else 0.0) + min(c.conf, 1.0)
            cur = dedup.get(c.text)
            if cur is None:
                dedup[c.text] = c
            else:
                cur.score += 0.5 * min(c.score, 3.0)
                cur.conf = max(cur.conf, c.conf)
        ranked = sorted(dedup.values(), key=lambda c: -c.score)[:MAX_CANDIDATES]

        # best: نخست کاندیدای معتبرِ بالای آستانهٔ کاربر؛ وگرنه هر معتبری؛
        # وگرنه نخستین کاندیدا (نمایش + هشدار اطمینان در UI)
        best = (next((c for c in ranked if c.valid and c.conf >= min_conf), None)
                or next((c for c in ranked if c.valid), None)
                or (ranked[0] if ranked else None))

        # برش و رنگ پلاک برای نمایش (از تصویر خام — همان مسیر OCR)
        plate_items = []
        best_crop = None
        for c in ranked:
            crop_b64 = None
            if c.box is not None:
                crop = self._plate_crop(bgr, c.box)
                if crop is not None:
                    crop_b64 = _to_b64_jpeg(crop)
                    if best is not None and c.text == best.text and best_crop is None:
                        best_crop = crop
            color, cscore = ("unknown", 0.0)
            if c.box is not None:
                x1, y1, x2, y2 = expand_box(c.box)
                crop_c = bgr[max(0, y1):int(y2), max(0, x1):int(x2)]
                if crop_c.size:
                    color, cscore = detect_plate_color(crop_c)
            plate_items.append({
                "raw": c.text,
                "persian": pt.format_plate(c.text),
                "system": pt.to_system_normalized(c.text),
                "valid": c.valid,
                "confidence": round(c.conf, 3),
                "method": c.method,
                "color": PLATE_COLORS_FA.get(color, color),
                "color_score": cscore,
                "box": [int(v) for v in c.box] if c.box else None,
                "crop_b64": crop_b64,
            })

        annotated_b64 = None
        if want_annotated:
            annotated_b64 = _to_b64_jpeg(_annotate(bgr, ranked, best))

        ms = round((time.perf_counter() - t0) * 1000)
        best_item = None
        if best is not None:
            best_item = next((item for c, item in zip(ranked, plate_items)
                              if c.text == best.text), None)
        if best_item is None and plate_items:
            best_item = plate_items[0]
        timings = {
            "detect_ms": detect_ms,
            "ocr_crops_ms": int(ocr_crops_ms * 1000),
            "fullimage_ms": int(fullimage_ms * 1000),
            "total_ms": ms,
        }
        return {
            "success": bool(plate_items),
            "best": best_item,
            "plates": plate_items,
            "engine": {
                "detector": "yolo" if caps["yolo_weights"] and caps["ultralytics"] else "classical",
                "ocr": "crnn+easyocr" if (caps["crnn_weights"] and caps["torch"]) else "easyocr",
                "easyocr_error": self._easy_err,
                "yolo_error": self._yolo_err if self._yolo_err != "weights-missing" else None,
                "fast_mode": fast_mode,
                "fullimage_skipped": fullimage_skipped,
                "timings": timings,
            },
            "elapsed_ms": ms,
            "annotated_b64": annotated_b64,
        }


# ---------------------------------------------------------------------------
# کمکی‌های خروجی
# ---------------------------------------------------------------------------
def _to_b64_jpeg(img, quality: int = 88) -> str | None:
    try:
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        return base64.b64encode(buf.tobytes()).decode("ascii") if ok else None
    except Exception:
        return None


def _annotate(bgr, ranked: list[_Candidate], best: _Candidate | None):
    """رسم جعبه‌ها + متن سیستم (ASCII — قابل اعتماد بدون فونت فارسی)."""
    out = bgr.copy()
    for c in ranked:
        if c.box is None:
            continue
        x1, y1, x2, y2 = [int(v) for v in c.box]
        color = (0, 200, 0) if c.valid else (0, 0, 230)
        if best is not None and c.text == best.text:
            cv2.rectangle(out, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), (0, 255, 255), 2)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        sys_form = pt.to_system_normalized(c.text) or c.text
        label = f"{sys_form} {c.conf:.0%}" if c.valid else f"? {sys_form[:14]} {c.conf:.0%}"
        y_text = max(22, y1 - 8)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(out, (x1, y_text - th - 6), (x1 + tw + 6, y_text + 4), color, -1)
        cv2.putText(out, label, (x1 + 3, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (255, 255, 255), 2)
    return out


# ---------------------------------------------------------------------------
# سینگلتون سطح ماژول
# ---------------------------------------------------------------------------
_reader: PlateReader | None = None
_reader_lock = threading.Lock()


def get_reader(models_dir: str = "models") -> PlateReader:
    global _reader
    with _reader_lock:
        if _reader is None:
            _reader = PlateReader(models_dir)
        return _reader
