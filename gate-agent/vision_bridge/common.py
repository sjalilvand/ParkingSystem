"""مشترکات Vision Bridge: خواندن .env، ارسال به بک‌اند، dedup، لاگ."""
import os
import re
import sys
import time
import uuid
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _load_env():
    env = AGENT_DIR / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
_load_env()

BACKEND_API  = os.environ.get("CENTRAL_API_URL", "http://127.0.0.1:8000/api/v1")
GATE_CODE    = os.environ.get("GATE_CODE", "GATE-IN-01")
GATE_API_KEY = os.environ.get("GATE_API_KEY", "gate-dev-key")
DEFAULT_DIR  = os.environ.get("DEFAULT_DIRECTION", "IN")
PRC_TOKEN    = os.environ.get("PRC_API_TOKEN", "").strip()
PRC_URL      = "https://api.platerecognizer.com/v1/plate-reader/"
CAPTURE_DIR  = AGENT_DIR.parent / "logs" / "captures"

_FA_AR = "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669"
_DIG   = str.maketrans(_FA_AR, "01234567890123456789")


def norm_key(s):
    """کلید dedup: فقط A-Z و 0-9 (بدون regex — امن و ساده)."""
    s = (s or "").translate(_DIG).upper()
    return "".join(ch for ch in s if ("A" <= ch <= "Z") or ("0" <= ch <= "9"))


def log(msg):
    line = "[{}] {}".format(time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        d = AGENT_DIR.parent / "logs"
        d.mkdir(exist_ok=True)
        (d / "vision.log").open("a", encoding="utf-8").write(line + "\n")
    except Exception:
        pass


_last_emit = {}


def should_emit(key, ttl=8.0):
    """جلوگیری از ارسال تکراری یک پلاک در فاصله کوتاه."""
    now = time.monotonic()
    prev = _last_emit.get(key)
    if prev and (now - prev) < ttl:
        return False
    _last_emit[key] = now
    return True


def post_detection(plate_raw, gate_code=None, direction=None, confidence=None, source="vision-bridge"):
    import httpx
    payload = {
        "gate_code": gate_code or GATE_CODE,
        "direction": direction or DEFAULT_DIR,
        "plate_raw": plate_raw,
        "source_event_id": str(uuid.uuid4()),
        "confidence": confidence or 90.0,
        "raw_payload": {"source": source},
    }
    try:
        r = httpx.post(
            BACKEND_API + "/gate/events/plate-detected",
            json=payload,
            headers={"X-API-Key": GATE_API_KEY, "Content-Type": "application/json"},
            timeout=8.0,
        )
        data = r.json() if r.status_code == 200 else None
        log("POST plate={!r} -> {} decision={}".format(
            plate_raw, r.status_code, data.get("decision") if data else r.text[:80]))
        return data
    except Exception as exc:
        log("POST FAILED plate={!r}: {}: {}".format(plate_raw, type(exc).__name__, exc))
        return None


def save_capture(img_bytes, tag):
    try:
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        p = CAPTURE_DIR / "{}_{}.jpg".format(tag, int(time.time()))
        p.write_bytes(img_bytes)
        return p
    except Exception:
        return None


def recognize_prc(img_bytes):
    """PlateRecognizer cloud. برمی‌گرداند: [{plate, score}]"""
    if not PRC_TOKEN:
        return []
    import httpx
    try:
        r = httpx.post(
            PRC_URL,
            files={"upload": ("frame.jpg", img_bytes, "image/jpeg")},
            headers={"Authorization": "Token " + PRC_TOKEN},
            timeout=25,
        )
        if r.status_code != 200:
            log("PRC HTTP {}: {}".format(r.status_code, r.text[:120]))
            return []
        return [{"plate": it.get("plate"), "score": float(it.get("score") or 0)}
                for it in r.json().get("results", [])]
    except Exception as exc:
        log("PRC FAILED: {}: {}".format(type(exc).__name__, exc))
        return []