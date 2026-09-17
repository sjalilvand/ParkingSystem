"""سناریو B: دوربین IP با استریم RTSP + موتور PlateRecognizer.
اجرا:  python -m vision_bridge.rtsp_reader
نیاز:  RTSP_URL=rtsp://user:pass@IP:554/...  و  PRC_API_TOKEN=...
"""
import os
import time

import cv2

from .common import log, norm_key, post_detection, recognize_prc, save_capture, should_emit


def main():
    url = os.environ.get("RTSP_URL", "").strip()
    if not url:
        print("!! RTSP_URL در .env تنظیم نشده است")
        return
    if not os.environ.get("PRC_API_TOKEN", "").strip():
        print("!! PRC_API_TOKEN تنظیم نشده - تشخیص ابری کار نمی‌کند")
    interval = float(os.environ.get("SCAN_INTERVAL", "1.5"))
    gate = os.environ.get("RTSP_GATE_CODE") or os.environ.get("GATE_CODE", "GATE-IN-01")
    direction = os.environ.get("RTSP_DIRECTION") or os.environ.get("DEFAULT_DIRECTION", "IN")

    log("RTSP connect: {}".format(url))
    cap = cv2.VideoCapture(url)
    last_scan = 0.0
    fail = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            fail += 1
            if fail % 30 == 1:
                log("RTSP read failed x{} - reconnecting...".format(fail))
            if fail > 60:
                cap.release()
                time.sleep(3)
                cap = cv2.VideoCapture(url)
                fail = 0
            time.sleep(0.05)
            continue
        fail = 0
        now = time.monotonic()
        if now - last_scan < interval:
            continue
        last_scan = now
        okj, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not okj:
            continue
        for it in recognize_prc(buf.tobytes()):
            plate = it.get("plate")
            if not plate:
                continue
            key = norm_key(plate)
            if not key or not should_emit(key):
                continue
            save_capture(buf.tobytes(), "rtsp_" + key)
            log("RTSP recognized: {!r} score={}".format(plate, it.get("score")))
            post_detection(plate, gate_code=gate, direction=direction,
                           confidence=round(it.get("score", 0) * 100, 1), source="rtsp")


if __name__ == "__main__":
    main()