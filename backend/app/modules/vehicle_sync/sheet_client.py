"""الحاقیه §۴ — کلاینت Google Sheets API v4 با حساب سرویس فقط‌خواندنی.

پیاده‌سازی سبک و آفلاین‌پسند: JWT RS256 با pyjwt + cryptography، تبادل توکن و
خواندن مقادیر با httpx. هیچ وابستگی به google-api-python-client ندارد.

احراز: فایل JSON حساب سرویس (GOOGLE_SERVICE_ACCOUNT_FILE) یا محتوای مستقیم
(GOOGLE_SERVICE_ACCOUNT_JSON). دامنه فقط https://www.googleapis.com/auth/spreadsheets.readonly
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx
import jwt

from app.core.config import settings

TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsError(RuntimeError):
    pass


@dataclass
class ServiceAccount:
    client_email: str
    private_key: str
    token_uri: str = TOKEN_URL


def load_service_account() -> ServiceAccount:
    raw = (settings.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
    if not raw:
        path = (settings.GOOGLE_SERVICE_ACCOUNT_FILE or "").strip()
        if path:
            try:
                with open(path, encoding="utf-8") as fh:
                    raw = fh.read()
            except OSError as exc:
                raise SheetsError(f"فایل حساب سرویس خوانده نشد: {exc}") from exc
    if not raw:
        raise SheetsError(
            "حساب سرویس Google تنظیم نشده — GOOGLE_SERVICE_ACCOUNT_FILE یا "
            "GOOGLE_SERVICE_ACCOUNT_JSON را در .env مقدار بدهید")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SheetsError(f"JSON حساب سرویس نامعتبر است: {exc}") from exc
    if "client_email" not in data or "private_key" not in data:
        raise SheetsError("فیلدهای client_email/private_key در حساب سرویس نیست")
    return ServiceAccount(client_email=data["client_email"],
                          private_key=data["private_key"],
                          token_uri=data.get("token_uri", TOKEN_URL))


_token_cache: dict[str, tuple[float, str]] = {}


async def get_access_token(sa: ServiceAccount | None = None) -> str:
    """توکن دسترسی با کش ۵۰ دقیقه‌ای (عمر توکن گوگل ۶۰ دقیقه)."""
    sa = sa or load_service_account()
    cached = _token_cache.get(sa.client_email)
    if cached and cached[0] > time.time():
        return cached[1]
    now = int(time.time())
    assertion = jwt.encode(
        {"iss": sa.client_email, "scope": SCOPE, "aud": sa.token_uri,
         "iat": now, "exp": now + 3500},
        sa.private_key, algorithm="RS256")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(sa.token_uri, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        })
    if resp.status_code != 200:
        raise SheetsError(f"دریافت توکن گوگل ناموفق: {resp.status_code} {resp.text[:200]}")
    token = resp.json().get("access_token")
    if not token:
        raise SheetsError("توکن دسترسی در پاسخ گوگل نبود")
    _token_cache[sa.client_email] = (time.time() + 3000, token)
    return token


async def fetch_sheet_rows(spreadsheet_id: str | None = None,
                           worksheet: str | None = None) -> dict:
    """خواندن کامل شیت: {"headers": [...], "rows": [[...], ...]} — فقط‌خواندنی."""
    sid = (spreadsheet_id or settings.GOOGLE_SHEETS_SPREADSHEET_ID or "").strip()
    ws = (worksheet or settings.GOOGLE_SHEETS_WORKSHEET or "خودروها").strip()
    if not sid:
        raise SheetsError("شناسهٔ Google Sheet تنظیم نشده است")
    token = await get_access_token()
    from urllib.parse import quote
    rng = quote(f"'{ws}'")
    url = f"{SHEETS_BASE}/{sid}/values/{rng}?valueRenderOption=UNFORMATTED_VALUE"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        raise SheetsError(
            f"خواندن شیت ناموفق: {resp.status_code} {resp.text[:300]} "
            f"(کاربر نکته: سرویس‌اکانت باید فقط‌خواندنی روی شیت اشتراک شود)")
    values = resp.json().get("values") or []
    if not values:
        return {"headers": [], "rows": []}
    headers = [str(h).strip() for h in values[0]]
    rows = [r for r in values[1:] if any(str(c).strip() for c in r)]
    return {"headers": headers, "rows": rows}


async def test_connection(spreadsheet_id: str | None = None) -> dict:
    """تست اتصال برای پنل تنظیمات — بدون نوشتن (فقط‌خواندنی)."""
    sid = (spreadsheet_id or settings.GOOGLE_SHEETS_SPREADSHEET_ID or "").strip()
    try:
        sa = load_service_account()
    except SheetsError as exc:
        return {"ok": False, "error": str(exc)}
    try:
        token = await get_access_token(sa)
        url = f"{SHEETS_BASE}/{sid}?fields=properties.title,sheets.properties.title"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            return {"ok": False, "error": f"{resp.status_code} {resp.text[:200]}"}
        data = resp.json()
        tabs = [s.get("properties", {}).get("title") for s in data.get("sheets", [])]
        return {"ok": True, "title": data.get("properties", {}).get("title"),
                "tabs": tabs, "service_account": sa.client_email}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
