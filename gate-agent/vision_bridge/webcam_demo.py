"""سناریو C: دموی وبکم - SPACE=عکس+تشخیص، I/O=ورود/خروج، ESC=خروج.
اجرا:  python -m vision_bridge.webcam_demo
با PRC_API_TOKEN تشخیص خودکار؛ بدون توکن، تایپ دستی پلاک (تست زنجیره).
"""
import os

import cv2

from .common import DEFAULT_DIR, GATE_CODE, log, norm_key, post_detection, recognize_prc, save_capture, should_emit


def main():
    idx = int(os.environ.get("WEBCAM_INDEX", "0"))
    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("!! وبکم index={} باز نشد - WEBCAM_INDEX را تغییر دهید".format(idx))
        return
    has_prc = bool(os.environ.get("PRC_API_TOKEN", "").strip())
    direction = DEFAULT_DIR
    gate = GATE_CODE
    print("=" * 60)
    print(" ParkingSystem Webcam ANPR Demo")
    print(" gate={} | direction={} | auto-OCR={}".format(gate, direction, "ON" if has_prc else "OFF (manual)"))
    print(" SPACE=تشخیص پلاک | I=ورود | O=خروج | ESC=خروج")
    print("=" * 60)

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        banner = "gate={} dir={} {}".format(gate, direction, "[AUTO-OCR]" if has_prc else "[MANUAL]")
        cv2.putText(frame, banner, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("ParkingSystem - SPACE=capture, I=IN, O=OUT, ESC=quit", frame)
        k = cv2.waitKey(30) & 0xFF
        if k == 27:
            break
        elif k in (ord("i"), ord("I")):
            direction, gate = "IN", os.environ.get("GATE_CODE", "GATE-IN-01")
            print(">> direction=IN gate={}".format(gate))
        elif k in (ord("o"), ord("O")):
            direction, gate = "OUT", os.environ.get("RTSP_GATE_CODE", "GATE-OUT-01")
            print(">> direction=OUT gate={}".format(gate))
        elif k == 32:
            okj, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not okj:
                continue
            img = buf.tobytes()
            save_capture(img, "webcam")
            results = recognize_prc(img) if has_prc else []
            if results:
                best = max(results, key=lambda r: r.get("score", 0))
                plate, conf = best["plate"], round(best.get("score", 0) * 100, 1)
                print(">> OCR: {!r} (confidence={}%)".format(plate, conf))
            else:
                plate = input(">> پلاک را تایپ کنید (مثلا 12 ب 345 ایران 67): ").strip()
                conf = None
                if not plate:
                    continue
            key = norm_key(plate)
            if not should_emit(key, ttl=3):
                print("   (تکراری - skip)")
                continue
            res = post_detection(plate, gate_code=gate, direction=direction, confidence=conf, source="webcam")
            if res:
                print("   DECISION: {} | barrier: {} | reason: {}".format(
                    res.get("decision"), res.get("barrier_action"), res.get("decision_reason")))
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()