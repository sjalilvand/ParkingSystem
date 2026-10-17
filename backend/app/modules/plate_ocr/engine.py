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

import numpy as np

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
MIN_CANDIDATE_CONF = 0.20          # حداقل اطمینان OCR برای ورود به کاندیداها
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
    min_h, max_h = int(h * 0.030), int(h * 0.35)
    for m in masks:
        closed = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                                  cv2.getStructuringElement(cv2.MORPH_RECT, (21, 5)))
        cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            x, y, cw, ch = cv2.boundingRect(c)
            if not (min_h <= ch <= max_h) or cw < ch * 1.8:
                continue
            aspect = cw / float(ch)
            if not (2.2 <= aspect <= 7.5):
                continue
            area_ratio = cw * ch / float(w * h)
            if area_ratio < 0.002:
                continue
            solidity = cw * ch / max(cv2.contourArea(c), 1.0)
            if solidity > 1.6:
                continue
            boxes.append((x / scale, y / scale, (x + cw) / scale, (y + ch) / scale))

    # حذف جعبه‌های هم‌پوشان
    boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    keep: list[tuple] = []
    for b in boxes:
        if all(_iou(b, k) < 0.30 for k in keep):
            keep.append(b)
    return keep[:6]


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
    def _ocr_crop(self, crop) -> list[tuple[str, float, str]]:
        """همه کاندیداهای متنی یک برش پلاک — (متن، اطمینان، روش)."""
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
                    res = easy.readtext(crop, detail=1, paragraph=False,
                                        allowlist=pt.OCR_ALLOWLIST)
                if res:
                    pieces = [(float(bb[0][0]), txt, float(c)) for bb, txt, c in res]
                    # حذف قطعات بلندِ بدون رقم — باقیمانده‌های متن صحنه/کلمه ایرانِ ناخوانا
                    # (پلاک همیشه رقم دارد؛ فقط قطعات کوتاه ۱-۲ نویسه‌ای حرف می‌توانند معتبر باشند)
                    pieces = [p for p in pieces
                              if p[2] >= MIN_CANDIDATE_CONF
                              and (any(ch.isdigit() for ch in p[1]) or len(p[1]) <= 2)]
                    if pieces:
                        rtl = "".join(t for _, t, _ in sorted(pieces, key=lambda p: -p[0]))
                        ltr = "".join(t for _, t, _ in sorted(pieces, key=lambda p: p[0]))
                        conf = max(p[2] for p in pieces)
                        out.append((rtl, conf, "easyocr"))
                        if ltr != rtl:
                            out.append((ltr, conf, "easyocr-ltr"))
            except Exception:
                pass
        return out

    # ------------------------------------------------ تشخیص
    def _detect(self, bgr) -> list[tuple]:
        """[(box, warp|None), ...] — YOLO اگر موجود، وگرنه کلاسیک."""
        yolo = self._get_yolo()
        if yolo is not None:
            try:
                res = yolo(bgr, conf=DET_CONF, verbose=False)[0]
                if res.boxes is not None and len(res.boxes):
                    return [(tuple(b), None)
                            for b in res.boxes.xyxy.cpu().numpy().astype(int)]
            except Exception:
                pass
        return [(b, None) for b in _classical_detect(bgr)]

    # ------------------------------------------------ برش پلاک
    def _plate_crop(self, bgr, box) -> "np.ndarray | None":
        """برش + راست‌کردن (warp) — برای CRNN و OCR دقیق."""
        x1, y1, x2, y2 = expand_box(box)
        H, W = bgr.shape[:2]
        crop = bgr[max(0, y1):min(H, y2), max(0, x1):min(W, x2)]
        if crop.size == 0 or crop.shape[0] < 10 or crop.shape[1] < 30:
            return None
        crop = _upscale_to(enhance(crop), 96)
        return _upscale_to(warp_plate(crop), 110)

    def _plain_crop(self, bgr, box) -> "np.ndarray | None":
        """برش ساده بدون وارپ — وقتی گوشه‌یاب خطا می‌رود این مسیر بهتر می‌خواند."""
        x1, y1, x2, y2 = expand_box(box)
        H, W = bgr.shape[:2]
        crop = bgr[max(0, y1):min(H, y2), max(0, x1):min(W, x2)]
        if crop.size == 0 or crop.shape[0] < 10 or crop.shape[1] < 30:
            return None
        return _upscale_to(enhance(crop), 110)

    # ------------------------------------------------ نقطه ورود
    def read_image(self, bgr, *, min_conf: float = 0.25,
                   want_annotated: bool = True) -> dict:
        """تحلیل کامل یک تصویر → دیکشنری نتیجه (JSON-serializable)."""
        t0 = time.perf_counter()
        caps = capabilities(self.models_dir)

        # محدود کردن اندازه برای کنترل زمان CPU
        H, W = bgr.shape[:2]
        if max(H, W) > 2600:
            f = 2600.0 / max(H, W)
            bgr = cv2.resize(bgr, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)

        enhanced = enhance(bgr)
        cands: list[_Candidate] = []

        dets = self._detect(enhanced)
        method_prefix = "yolo" if self._get_yolo() is not None else "classical"
        for i, (box, _warp) in enumerate(dets):
            # دو مسیر برش: وارپ‌شده + ساده (هرکدام ممکن است بهتر خوانده شود)
            crops = [(self._plate_crop(enhanced, box), "warp"),
                     (self._plain_crop(enhanced, box), "crop")]
            for crop, crop_kind in crops:
                if crop is None:
                    continue
                for text, conf, ocr_method in self._ocr_crop(crop):
                    if conf < min(min_conf, MIN_CANDIDATE_CONF) + 0.05:
                        continue
                    norm, valid = pt.validate(text)
                    if not valid and len(norm) in (6, 8):
                        fixed = pt.enforce_format(norm)
                        if pt.validate(fixed)[1]:
                            cands.append(_Candidate(fixed, conf * 0.95,
                                                    f"{method_prefix}+{ocr_method}+{crop_kind}+enforce",
                                                    True, box, None))
                    cands.append(_Candidate(norm, conf,
                                            f"{method_prefix}+{ocr_method}+{crop_kind}",
                                            valid, box, None))

        # مسیر جایگزین: OCR روی کل تصویر — فقط وقتی از برش‌ها کاندیدای معتبر نداریم
        # (روی صحنه‌های شلوغ گران و پر از متن مزاحم است)
        if not any(c.valid for c in cands):
            fi = enhanced
            H2, W2 = fi.shape[:2]
            if max(H2, W2) > 1600:                     # کنترل هزینه OCR کل-تصویر
                f2 = 1600.0 / max(H2, W2)
                fi = cv2.resize(fi, None, fx=f2, fy=f2, interpolation=cv2.INTER_AREA)
            for text, conf, m in self._ocr_crop(fi):
                if conf < min_conf:
                    continue
                norm, valid = pt.validate(text)
                if not valid and len(norm) in (6, 8):
                    fixed = pt.enforce_format(norm)
                    if pt.validate(fixed)[1]:
                        cands.append(_Candidate(fixed, conf * 0.95, f"fullimage+{m}+enforce",
                                                True, None, None))
                cands.append(_Candidate(norm, conf, f"fullimage+{m}", valid, None, None))

        # حذف تکراری + امتیازدهی (معتبر بودن مهم‌تر از اطمینان)
        dedup: dict[str, _Candidate] = {}
        for c in cands:
            if not c.text or len(c.text) < 5 or len(c.text) > 9:
                continue    # پلاک ایران ۶/۸ نویسه است؛ خارج از بازه نزدیک = نویز صحنه
            c.score = (2.0 if c.valid else 0.0) + min(c.conf, 1.0)
            cur = dedup.get(c.text)
            if cur is None or c.score > cur.score:
                dedup[c.text] = c
        ranked = sorted(dedup.values(), key=lambda c: -c.score)[:MAX_CANDIDATES]

        best = next((c for c in ranked if c.valid), None) or (ranked[0] if ranked else None)

        # برش و رنگ پلاک برای نمایش
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
        return {
            "success": bool(plate_items),
            "best": best_item,
            "plates": plate_items,
            "engine": {
                "detector": "yolo" if caps["yolo_weights"] and caps["ultralytics"] else "classical",
                "ocr": "crnn+easyocr" if (caps["crnn_weights"] and caps["torch"]) else "easyocr",
                "easyocr_error": self._easy_err,
                "yolo_error": self._yolo_err if self._yolo_err != "weights-missing" else None,
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
