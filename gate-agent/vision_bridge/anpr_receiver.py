"""سناریو A: دریافت رویداد از دوربین‌های پلاک‌خوان ANPR (Hikvision/Dahua/عمومی).
اجرا:  python -m vision_bridge.anpr_receiver
تنظیم دوربین: POST به http://<IP-این-سیستم>:8092/anpr  (یا /anpr/GATE-OUT-01/OUT)
"""
import os
import re

import uvicorn
from fastapi import FastAPI, Request

from .common import log, norm_key, post_detection, should_emit

app = FastAPI(title="ParkingSystem ANPR Receiver", docs_url=None, redoc_url=None)

_PLATE_KEYS = ["plate", "plateNumber", "plate_number", "plateNo", "plate_no",
               "licensePlate", "license_plate", "PlateNo", "LPNumber", "carNumber"]


def _dig_json(obj):
    keys = {k.lower() for k in _PLATE_KEYS}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in keys and isinstance(v, str) and v.strip():
                return v.strip()
            r = _dig_json(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _dig_json(v)
            if r:
                return r
    return None


def _extract_from_text(text):
    alt = "|".join(re.escape(k) for k in _PLATE_KEYS)
    m = re.search(rf"\"(?:{alt})\"\s*:\s*\"([^\"]+)\"", text, re.I)
    if m:
        return m.group(1)
    m = re.search(rf"<(?:{alt})>([^<]+)</", text, re.I)
    if m:
        return m.group(1)
    return None


@app.get("/health")
async def health():
    return {"ok": True, "service": "anpr-receiver"}


@app.post("/anpr")
@app.post("/anpr/{gate}/{direction}")
async def anpr(request: Request, gate: str | None = None, direction: str | None = None):
    raw = (await request.body()).decode("utf-8", "replace")
    plate = None
    if "json" in request.headers.get("content-type", "").lower():
        try:
            plate = _dig_json(await request.json())
        except Exception:
            pass
    if not plate:
        plate = _extract_from_text(raw)
    if not plate:
        log("ANPR payload without plate: {!r}".format(raw[:160]))
        return {"ok": False, "error": "PLATE_NOT_FOUND_IN_PAYLOAD"}

    key = norm_key(plate)
    if not should_emit(key):
        return {"ok": True, "deduped": True}

    log("ANPR camera plate: {!r} gate={} dir={}".format(plate, gate or "-", direction or "-"))
    res = post_detection(plate, gate_code=gate, direction=direction, source="anpr-http")
    return {"ok": res is not None, "decision": (res or {}).get("decision")}


if __name__ == "__main__":
    port = int(os.environ.get("ANPR_PORT", "8092"))
    log("ANPR receiver listening on 0.0.0.0:{}".format(port))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")