"""تشخیص زندهٔ دوربین‌های گیت — داخل کانتینر اجرا کنید:

    docker exec parkingsystem-prod-backend-1 python -m scripts.cam_probe

بررسی می‌کند:
  ۱) پیکربندی ذخیره‌شدهٔ دوربین‌ها در دیتابیس (URL فعال هر سمت)
  ۲) دسترسی TCP به دوربین‌ها (پورت RTSP و HTTP)
  ۳) مسیر HTTP snapshot (/jpgimage/1/image.jpg) با زنجیرهٔ احراز + رزولوشن
  ۴) مسیرهای RTSP (main/sub) — چند فریم واقعی decode می‌شود؟ + رزولوشن
خروجی را کامل برای پشتیبانی بفرستید.
"""
from __future__ import annotations

import asyncio
import re
import socket
import urllib.parse


def _mask(url: str) -> str:
    return re.sub(r"(://[^:/@]+:)([^@]+)(@)", r"\1***\3", url or "")


def _host_port(url: str, default_port: int) -> tuple[str, int]:
    p = urllib.parse.urlsplit(url.strip())
    return (p.hostname or "", p.port or default_port)


def tcp_test(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def http_test(url: str, label: str) -> None:
    from app.modules.camera.poller import _fetch_jpeg_sync
    import cv2
    import numpy as np

    jpg = _fetch_jpeg_sync(url, timeout=6.0)
    if jpg is None:
        print(f"  {label}: FAIL — JPEG واقعی دریافت نشد (auth/آدرس/فیلتر)")
        return
    frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
    size = f"{frame.shape[1]}x{frame.shape[0]}" if frame is not None else "?"
    print(f"  {label}: OK — {len(jpg)} bytes، JPEG واقعی، رزولوشن {size}")


def rtsp_test(url: str, label: str, frames_want: int = 5) -> None:
    import cv2

    cap = cv2.VideoCapture()
    try:
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
    except Exception:
        pass
    try:
        cap.open(url, cv2.CAP_FFMPEG)
    except Exception as exc:  # noqa: BLE001
        print(f"  {label}: FAIL — exception {type(exc).__name__}")
        return
    if not cap.isOpened():
        print(f"  {label}: FAIL — open نشد")
        return
    got, size = 0, None
    for _ in range(20):
        ok, f = cap.read()
        if ok and f is not None:
            got += 1
            size = f"{f.shape[1]}x{f.shape[0]}"
            if got >= frames_want:
                break
    cap.release()
    verdict = "OK" if got >= frames_want else ("ضعیف" if got else "FAIL")
    print(f"  {label}: {verdict} — {got} فریم decode شد، رزولوشن {size}")


async def _load_cfg() -> dict:
    from app.db.session import AsyncSessionLocal
    from app.modules.camera import config_store

    async with AsyncSessionLocal() as db:
        return await config_store.load_cameras(db)


def main() -> None:
    import os

    print("=" * 64)
    print("cam_probe — تشخیص زندهٔ دوربین‌های گیت")
    print("=" * 64)

    # ۱) پیکربندی DB
    cfg = asyncio.run(_load_cfg())
    print("\n[۱] پیکربندی ذخیره‌شده (AppSetting 'cameras'):")
    for side in ("IN", "OUT"):
        s = cfg.get(side) or {}
        url = s.get("rtsp") or ""
        print(f"  {side}: enabled={s.get('enabled')}  rtsp={_mask(url) or '(خالی)'}"
              f"  gate={s.get('gate_code') or '-'} dir={s.get('direction') or '-'}")
    print(f"  poll_interval={cfg.get('poll_interval')}s  ocr={cfg.get('ocr')}")

    # ۲) TCP
    print("\n[۲] دسترسی TCP:")
    for host in ("192.168.100.230", "192.168.100.231"):
        for port, name in ((554, "RTSP"), (80, "HTTP"), (8999, "ONVIF")):
            ok = tcp_test(host, port)
            print(f"  {host}:{port} ({name}): {'OPEN' if ok else 'CLOSED/UNREACH'}")

    # ۳) HTTP snapshot — آدرس تأییدشدهٔ کاربر
    print("\n[۳] HTTP snapshot /jpgimage/1/image.jpg:")
    for host in ("192.168.100.230", "192.168.100.231"):
        u = "admin"
        p = "admin"
        http_test(f"http://{u}:{p}@{host}/jpgimage/1/image.jpg", f"  {host}")

    # ۴) RTSP — main و sub (H265 بررسی می‌شود)
    print("\n[۴] RTSP (توجه: استریم دوربین H265 است):")
    for host in ("192.168.100.230", "192.168.100.231"):
        base = f"rtsp://admin:admin@{host}:554"
        rtsp_test(f"{base}/h264/ch1/main/av_stream", f"{host} main")
        rtsp_test(f"{base}/h264/ch1/sub/av_stream", f"{host} sub")

    # ۵) URLهای پیکربندی‌شده — واقعاً کار می‌کنند؟
    print("\n[۵] تست URLهای پیکربندی‌شده:")
    for side in ("IN", "OUT"):
        s = cfg.get(side) or {}
        url = (s.get("rtsp") or "").strip()
        if not url:
            print(f"  {side}: پیکربندی نشده")
            continue
        if url.lower().startswith(("http://", "https://")):
            http_test(url, f"  {side} (HTTP)")
        else:
            rtsp_test(url, f"  {side} (RTSP)")

    print("\nنکته: اگر [۳] OK بود ولی [۴] FAIL/ضعیف — دوربین را یک‌بار Power-cycle کنید")
    print("و در سامانه از آدرس HTTP استفاده کنید (تصویر HTTP همیشه کار می‌کند).")
    print("=" * 64)


if __name__ == "__main__":
    main()
