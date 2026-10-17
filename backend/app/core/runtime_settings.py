"""سیاست‌های زمان-اجرا (تصمیمات D1-D10) — خواندن از app_settings با fallback به env.

لایه‌بندی منبع مقدار هر سیاست (اولویت از بالا):
  1. جدول app_settings (کلید گروه، مقدار dict) — قابل تغییر از پنل مدیریت بدون ری‌استارت
  2. متغیر محیطی / config.py (Settings)
  3. مقدار پیش‌فرض امن (حفظ رفتار موجود)

گروه‌های کلید در app_settings:
  gate_policy    -> {"EXIT_UNPAID_POLICY": "ALLOW|WARN|DENY"}                       (D1)
  tariff_policy  -> {"rounding": "HOUR_UP|MINUTE", "day_definition": "24H|CALENDAR", (D2/D3)
                     "night_enabled": bool, "night_start_hour": int, "night_end_hour": int, (D4)
                     "min_charge_amount": int, "exit_grace_minutes": int}             (D7)
  finance_policy -> {"SELF_APPROVAL_POLICY": "WARN|BLOCK"}                          (D9)
  report_policy  -> {"VOIDED_REPORT_MODE": "SEPARATE|EXCLUDE"}                      (D10)

نکته ایمپورت: import ماژول config_admin درون تابع انجام می‌شود تا import چرخه‌ای
با app.main (که همه router ها را جمع می‌کند) رخ ندهد.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


async def get_policy_setting(
    db: AsyncSession,
    group_key: str,
    name: str,
    default=None,
    cast=None,
    aliases: list[str] | None = None,
):
    """خواندن یک سیاست از app_settings[group_key] با fallback به settings و default.

    aliases: کلیدهای جایگزین داخل dict ذخیره‌شده — چون config_admin.DEFAULTS از
    پیش کلیدهای lowercase (مثل «rounding») دارد و env-style نام‌ها UPPERCASE هستند،
    هر دو قالب پشتیبانی می‌شوند (اولویت با ترتیب فهرست).
    db فقط به execute نیاز دارد؛ در تست‌های واحد با FakeDB قابل استفاده است.
    هر خطا (جدول موجود نبودن در مهاجرت‌های قدیمی و ...) بی‌صدا به fallback می‌رود —
    سیاست هرگز نباید جریان اصلی گیت/مالی را بشکند.
    """
    try:
        from app.modules.config_admin.models import AppSetting
        row = (await db.execute(
            select(AppSetting).where(AppSetting.key == group_key)
        )).scalar_one_or_none()
    except Exception:
        row = None
    if row is not None:
        value = getattr(row, "value", None)
        if isinstance(value, dict):
            for key in ([name] + list(aliases or [])):
                if key in value and value[key] is not None:
                    raw = value[key]
                    try:
                        return cast(raw) if cast else raw
                    except (TypeError, ValueError):
                        break
    env_value = getattr(settings, name, None)
    if env_value is not None:
        return env_value
    return default


def _to_bool(raw) -> bool:
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on", "بله")
    return bool(raw)


_CALC_KEYS = ("rounding", "day_definition", "night_enabled",
              "night_start_hour", "night_end_hour", "min_charge_amount")


def tariff_calc_kwargs(policy: dict) -> dict:
    """تبدیل خروجی resolve_tariff_policy به kwargs مجاز برای calculate_amounts
    (exit_grace_minutes در محاسبه تعرفه نقش ندارد و نباید پاس داده شود)."""
    return {k: policy[k] for k in _CALC_KEYS if k in policy}


async def resolve_exit_policy(db: AsyncSession) -> str:
    """D1: سیاست خروج خودرو با بدهی — ALLOW | WARN | DENY (پیش‌فرض WARN)."""
    policy = await get_policy_setting(db, "gate_policy", "EXIT_UNPAID_POLICY", default="WARN")
    policy = (str(policy) or "WARN").upper()
    return policy if policy in ("ALLOW", "WARN", "DENY") else "WARN"


async def resolve_tariff_policy(db: AsyncSession) -> dict:
    """D2/D3/D4/D7: مجموعه سیاست‌های محاسبه تعرفه با مقادیر پیش‌فرضِ حفظ رفتار."""
    rounding = await get_policy_setting(
        db, "tariff_policy", "TARIFF_ROUNDING", default="HOUR_UP",
        aliases=["rounding"])
    day_def = await get_policy_setting(
        db, "tariff_policy", "TARIFF_DAY_DEFINITION", default="24H",
        aliases=["day_definition"])
    night_enabled = await get_policy_setting(
        db, "tariff_policy", "NIGHT_TARIFF_ENABLED", default=False, cast=_to_bool,
        aliases=["night_enabled"])
    night_start = await get_policy_setting(
        db, "tariff_policy", "NIGHT_START_HOUR", default=22, cast=int,
        aliases=["night_start_hour"])
    night_end = await get_policy_setting(
        db, "tariff_policy", "NIGHT_END_HOUR", default=6, cast=int,
        aliases=["night_end_hour"])
    min_charge = await get_policy_setting(
        db, "tariff_policy", "MIN_CHARGE_AMOUNT", default=0, cast=int,
        aliases=["min_charge_amount"])
    grace = await get_policy_setting(
        db, "tariff_policy", "EXIT_GRACE_MINUTES", default=20, cast=int,
        aliases=["exit_grace_minutes"])
    return {
        "rounding": rounding if rounding in ("HOUR_UP", "MINUTE") else "HOUR_UP",
        "day_definition": day_def if day_def in ("24H", "CALENDAR") else "24H",
        "night_enabled": bool(night_enabled),
        "night_start_hour": max(0, min(23, int(night_start or 22))),
        "night_end_hour": max(0, min(23, int(night_end or 6))),
        "min_charge_amount": max(0, int(min_charge or 0)),
        "exit_grace_minutes": max(0, int(grace or 0)),
    }


async def resolve_self_approval_policy(db: AsyncSession) -> str:
    """D9: ممنوعیت تأیید اصلاحیه توسط درخواست‌دهنده — WARN | BLOCK (پیش‌فرض WARN)."""
    policy = await get_policy_setting(db, "finance_policy", "SELF_APPROVAL_POLICY", default="WARN")
    policy = (str(policy) or "WARN").upper()
    return policy if policy in ("WARN", "BLOCK") else "WARN"


async def resolve_voided_report_mode(db: AsyncSession) -> str:
    """D10: تکلیف شارژ VOIDED در گزارش‌های مالی — SEPARATE | EXCLUDE (پیش‌فرض SEPARATE)."""
    mode = await get_policy_setting(db, "report_policy", "VOIDED_REPORT_MODE", default="SEPARATE")
    mode = (str(mode) or "SEPARATE").upper()
    return mode if mode in ("SEPARATE", "EXCLUDE") else "SEPARATE"
