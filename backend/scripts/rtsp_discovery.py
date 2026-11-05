#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rtsp_discovery.py — عیب‌یابی کامل دوربین گیت، مستقیم روی سرور داخل کانتینر

اجرا (PowerShell در E:\\ParkingSystem):
    docker compose -f docker-compose.prod.yml exec backend ^
        python scripts/rtsp_discovery.py 192.168.100.230 admin admin

خروجی عمداً انگلیسی است تا در کنسول ویندوز به‌هم نریزد.
چه چیزهایی بررسی می‌شود:
  ۱) پورت‌های TCP (554 RTSP، 80، 8899، 8080 ONVIF)
  ۲) RTSP خام با سوکت — کد واقعی پاسخ سرور (200/401/404) برای OPTIONS و
     DESCRIBE هر مسیر؛ این دقیقاً می‌گوید مشکل «مسیر» است یا «رمز»
  ۳) باز کردن با OpenCV/FFMPEG (همان چیزی که خود اپ استفاده می‌کند)
  ۴) ONVIF GetStreamUri — نشانی استریم را از خود دوربین می‌پرسد
  ۵) استریم/اسنپ‌شات MJPEG روی HTTP (راه جایگزین اگر RTSP کلاً بسته باشد)
"""
import base64
import hashlib
import os
import re
import socket
import sys
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.100.230"
USER = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASS = sys.argv[3] if len(sys.argv) > 3 else "admin"

RTSP_PATHS = [
    "", "/stream0", "/stream1", "/11", "/12", "/0", "/1/cif",
    "/h264/ch1/main/av_stream", "/Streaming/Channels/101",
    "/cam/realmonitor?channel=1&subtype=0", "/cam/realmonitor",
    "/live/ch00_0", "/live/ch0", "/media/video1", "/onvif1", "/onvif2",
    "/ch0_0.h264", "/live0.264", "/live1.264", "/h264_stream", "/av0_0",
    "/cam1/h264", "/ucast/11", "/h264/ch1/sub/av_stream", "/1/1",
    "/LiveMedia/ch1/stream1", "/LiveMedia/ch1/stream0",
]
XM_QUERIES = [
    f"user={USER}&password={PASS}&channel=1&stream=0.sdp?real_stream",  # xmeye رایج
    f"user={USER}_password={PASS}_channel=1_stream=0.sdp",              # امضای دیگر
]
MJ_HTTP_PATHS = [
    "/webcapture.jpg?command=snap&channel=1",           # snapshot XiongMai
    f"/videostream.cgi?user={USER}&pwd={PASS}",          # OEM کلاسیک MJPEG
    "/mjpg/video.mjpg",
    "/videostream.asf",
]
ONVIF_PORTS = (8899, 80, 8080)


def mask(url: str) -> str:
    """پوشاندن رمز در URL برای چاپ امن در لاگ."""
    out = re.sub(r"(://[^:/@\s]+:)[^@\s]+@", r"\1***@", url)
    out = re.sub(r"(password=)[^&\s]+", r"\1***", out, flags=re.I)
    out = re.sub(r"(pwd=)[^&\s]+", r"\1***", out, flags=re.I)
    return out


def tcp_open(port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((HOST, port), timeout=timeout):
            return True
    except OSError:
        return False


def rtsp_code(url: str, method: str, timeout: float = 4.0) -> tuple:
    """یک درخواست RTSP خام → (کد عددی، خط وضعیت). خرابی شبکه → (-1، دلیل)."""
    try:
        p = urlsplit(url)
        port = p.port or 554
        target = p.path or "/"
        if p.query:
            target += "?" + p.query
        sock = socket.create_connection((p.hostname, port), timeout=timeout)
        sock.settimeout(timeout)
        req = (f"{method} rtsp://{p.hostname}:{port}{target} RTSP/1.0\r\n"
               f"CSeq: 1\r\nUser-Agent: ParkingSystem-Diag\r\n")
        if p.username:
            cred = base64.b64encode(
                f"{p.username}:{p.password or ''}".encode()).decode()
            req += f"Authorization: Basic {cred}\r\n"
        if method == "DESCRIBE":
            req += "Accept: application/sdp\r\n"
        sock.sendall((req + "\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        sock.close()
        head = buf.split(b"\r\n\r\n", 1)[0].decode("latin-1", "replace")
        m = re.match(r"RTSP/1\.0\s+(\d{3})\s*(.*)", head)
        if m:
            return int(m.group(1)), m.group(2).strip()
        first = head.splitlines()[0] if head.splitlines() else "(empty reply)"
        return -2, first[:80]
    except socket.timeout:
        return -1, "timeout"
    except OSError as e:
        return -1, str(e)[:80]


def cv2_open(url: str, timeout_ms: int = 4000):
    """باز کردن با OpenCV/FFMPEG — خروجی: True/False یا None اگر cv2 نیست."""
    try:
        import cv2
    except ImportError:
        return None
    cap = cv2.VideoCapture()
    try:
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)
        if not cap.open(url, cv2.CAP_FFMPEG):
            return False
        ok, frame = cap.read()
        return bool(ok and frame is not None and frame.size > 0)
    except Exception:
        return False
    finally:
        try:
            cap.release()
        except Exception:
            pass


# ---------------------------------------------------------------------------
def section(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(4, 60 - len(title)))


def main() -> int:
    print(f"Gate camera diagnostic  host={HOST}  user={USER}  pass={'***'}")
    print(f"time: {datetime.now(timezone.utc).isoformat()}")

    section("1) TCP ports")
    for port in (554, 80, 8899, 8080):
        print(f"  port {port:<5} {'OPEN' if tcp_open(port) else 'closed/unreachable'}")

    section("2) Raw RTSP (real server response codes)")
    urls = [f"rtsp://{USER}:{PASS}@{HOST}:{RTSP_PORT}{q}" for q in XM_QUERIES]
    urls += [f"rtsp://{USER}:{PASS}@{HOST}:{RTSP_PORT}{p}" for p in RTSP_PATHS]
    urls += [f"rtsp://{HOST}:{RTSP_PORT}{p}" for p in ("", "/stream0", "/11")]
    describe_200: list[str] = []
    codes: dict[int, int] = {}
    for u in urls:
        c1, t1 = rtsp_code(u, "OPTIONS")
        c2, t2 = rtsp_code(u, "DESCRIBE")
        codes[c2] = codes.get(c2, 0) + 1
        flag = "  <== DESCRIBE OK" if c2 == 200 else ""
        print(f"  {mask(u)}\n      OPTIONS={c1} {t1} | DESCRIBE={c2} {t2}{flag}")
        if c2 == 200:
            describe_200.append(u)

    section("3) OpenCV/FFMPEG open test")
    working: list[str] = []
    order = describe_200 + [u for u in urls if u not in describe_200]
    for u in order[:30]:
        r = cv2_open(u)
        if r is None:
            print("  cv2 not installed — skipping section")
            break
        mark = "WORKS <<<" if r else "failed"
        print(f"  {mask(u)}  ->  {mark}")
        if r:
            working.append(u)
            break

    section("4) ONVIF GetStreamUri")
    onvif_uris: list[str] = []
    for port in ONVIF_PORTS:
        if not tcp_open(port, 1.5):
            print(f"  port {port}: closed")
            continue
        url = f"http://{HOST}:{port}/onvif/device_service"
        for digest_mode in (True, False):
            sec = _wsse(digest_mode)
            body = ('<s:Body><GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>'
                    "</s:Body>")
            resp = _onvif_post(url, sec + body)
            if "GetProfilesResponse" not in resp:
                print(f"  port {port} ({'digest' if digest_mode else 'plain'}): "
                      "no GetProfilesResponse")
                continue
            tokens = re.findall(r'\btoken="([^"]+)"', resp)
            print(f"  port {port}: ONVIF OK, profiles={tokens[:4]}")
            for tok in dict.fromkeys(tokens):
                body = ('<s:Body><GetStreamUri xmlns="http://www.onvif.org/ver10/media/wsdl">'
                        '<StreamSetup><Stream xmlns="http://www.onvif.org/ver10/schema">'
                        "RTP-Unicast</Stream><Transport xmlns="
                        '"http://www.onvif.org/ver10/schema"><Protocol>RTSP</Protocol>'
                        "</Transport></StreamSetup>"
                        f"<ProfileToken>{tok}</ProfileToken></GetStreamUri></s:Body>")
                resp2 = _onvif_post(url, sec + body)
                m = re.search(r"<(?:\w+:)?Uri>([^<]+)</(?:\w+:)?Uri>", resp2)
                if not m:
                    continue
                uri = m.group(1).strip()
                if "@" not in uri and uri.lower().startswith("rtsp://"):
                    parts = urlsplit(uri)
                    uri = (f"rtsp://{quote(USER)}:{quote(PASS)}@"
                           f"{parts.netloc}{parts.path}"
                           + (f"?{parts.query}" if parts.query else ""))
                print(f"  profile {tok}: {mask(uri)}")
                onvif_uris.append(uri)
            break
        if onvif_uris:
            break
    for uri in onvif_uris:
        r = cv2_open(uri)
        print(f"  cv2 test {mask(uri)} -> {'WORKS <<<' if r else 'failed'}")
        if r:
            working.append(uri)

    section("5) HTTP MJPEG / snapshot")
    basic = base64.b64encode(f"{USER}:{PASS}".encode()).decode()
    for path in MJ_HTTP_PATHS:
        url = f"http://{HOST}{path}"
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Basic {basic}"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                ctype = resp.headers.get("Content-Type", "?")
                data = resp.read(2048)
                ok = ctype.startswith(("image/", "multipart/", "video/", "application/octet-stream"))
                print(f"  {mask(url)}  HTTP {resp.status}  {ctype}  "
                      f"{'<== WORKS <<<' if ok else ''}")
                if ok:
                    working.append(url)
        except Exception as e:  # noqa: BLE001
            print(f"  {mask(url)}  ->  {str(e)[:70]}")

    section("VERDICT")
    if working:
        print("  WORKING URL:")
        for u in working:
            print(f"    {u}")          # کامل؛ برای وارد کردن در پنل
        return 0
    desc = ", ".join(f"DESCRIBE {k} x{v}" for k, v in sorted(codes.items()))
    print(f"  No working URL. RTSP summary: {desc or 'no replies'}")
    if codes.get(404) and not codes.get(401):
        print("  -> همهٔ پاسخ‌ها 404 است یعنی «مسیر» غلط است نه رمز؛")
        print("     اگر همهٔ مسیرهای بالا 404 دادند، سرویس RTSP این دوربین فقط")
        print("     با پارامترهای خاص خودش جواب می‌دهد — خروجی بخش 4 (ONVIF) و 5")
        print("     (MJPEG) را بفرستید.")
    elif codes.get(401):
        print("  -> پاسخ 401 یعنی رمز غلط است (نه مسیر).")
    return 1


def _wsse(digest_mode: bool) -> str:
    nonce = os.urandom(16)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if digest_mode:
        dig = base64.b64encode(
            hashlib.sha1(nonce + created.encode() + PASS.encode()).digest()).decode()
        pwd = ('<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/'
               f'oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{dig}'
               "</wsse:Password>")
    else:
        pwd = ('<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/'
               f'oasis-200401-wss-username-token-profile-1.0#PasswordText">{PASS}'
               "</wsse:Password>")
    return ('<s:Header><wsse:Security s:mustUnderstand="1" xmlns:wsse='
            '"http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
            f"<wsse:UsernameToken><wsse:Username>{USER}</wsse:Username>{pwd}"
            '<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/'
            'oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
            + base64.b64encode(nonce).decode() + "</wsse:Nonce>"
            '<wsu:Created xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/'
            'oasis-200401-wss-wssecurity-utility-1.0.xsd">' + created + "</wsu:Created>"
            "</wsse:UsernameToken></wsse:Security></s:Header>")


def _onvif_post(url: str, inner: str) -> str:
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
           'xmlns:tt="http://www.onvif.org/ver10/schema">' + inner + "</s:Envelope>")
    try:
        req = urllib.request.Request(
            url, data=xml.encode(),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


if __name__ == "__main__":
    sys.exit(main())
