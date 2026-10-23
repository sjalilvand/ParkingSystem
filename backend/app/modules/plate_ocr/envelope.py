"""الحاقیه §۳ — پاکت ثبت پلاک (زاویه/نور/سرعت) و مسیر تأیید انسانی.

سنجه‌های ثبت (capture envelope) مشخص می‌کنند که خوانش پلاک در چه محدوده‌ای
قابل اتکاست. خوانش خارج از پاکت یا با اطمینان پایین به‌جای تصمیم خودکار، به
صف تأیید انسانی (NEEDS_REVIEW) می‌رود و پلاک «ثبت‌نشده» تلقی می‌شود.

آستانه‌ها: env فقط fallback است؛ مقدار زمان-اجرا از app_settings خوانده می‌شود
(گروه plate_envelope) و بدون ری‌استارت از «طراح تنظیمات» قابل تغییر است.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.runtime_settings import get_policy_setting


@dataclass
class EnvelopeResult:
    ok: bool                      # داخل پاکت تأییدشده است؟
    review_required: bool         # نیاز به تأیید انسانی؟
    violations: list[str] = field(default_factory=list)
    thresholds: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


async def resolve_envelope_thresholds(db: AsyncSession) -> dict:
    """آستانه‌های پاکت — app_settings (گروه plate_envelope) با fallback به env."""
    async def g(key: str, default, cast):
        return await get_policy_setting(db, "plate_envelope", key, default=default, cast=cast)
    return {
        "max_angle_deg": await g("MAX_ANGLE_DEG", settings.PLATE_ENVELOPE_MAX_ANGLE_DEG, float),
        "min_lux": await g("MIN_LUX", settings.PLATE_ENVELOPE_MIN_LUX, float),
        "max_speed_kmh": await g("MAX_SPEED_KMH", settings.PLATE_ENVELOPE_MAX_SPEED_KMH, float),
        "low_conf": await g("REVIEW_LOW_CONF", settings.PLATE_REVIEW_LOW_CONF, float),
    }


async def evaluate_capture(
    db: AsyncSession,
    *,
    angle_deg: float | None = None,
    lux: float | None = None,
    speed_kmh: float | None = None,
    confidence: float | None = None,
    plate_normalized: str | None = None,
) -> EnvelopeResult:
    """ارزیابی پاکت ثبت.

    قواعد:
      * پلاک قابل نرمال‌سازی نبود (ثبت‌نشده) → تأیید انسانی
      * اطمینان زیر آستانه → تأیید انسانی
      * زاویه/نور/سرعت خارج از پاکت تأییدشده → تأیید انسانی (با ذکر نقض‌ها)
    مقادیر None (سنسور نداده) نقض حساب نمی‌شوند تا رفتار فعلی خراب نشود؛
    اما اطمینانِ ثبت‌شدهٔ پایین همیشه مسیر بازبینی را فعال می‌کند.
    """
    th = await resolve_envelope_thresholds(db)
    violations: list[str] = []

    if angle_deg is not None and abs(float(angle_deg)) > float(th["max_angle_deg"]):
        violations.append(f"ANGLE:{angle_deg}>{th['max_angle_deg']}")
    if lux is not None and float(lux) < float(th["min_lux"]):
        violations.append(f"LUX:{lux}<{th['min_lux']}")
    if speed_kmh is not None and float(speed_kmh) > float(th["max_speed_kmh"]):
        violations.append(f"SPEED:{speed_kmh}>{th['max_speed_kmh']}")

    low_conf = confidence is not None and float(confidence) < float(th["low_conf"])
    unknown_plate = not plate_normalized

    review_required = low_conf or unknown_plate or bool(violations)
    return EnvelopeResult(
        ok=not violations and not unknown_plate,
        review_required=review_required,
        violations=violations,
        thresholds=th,
    )


def review_status_for(confidence: float | None, env: EnvelopeResult | None) -> str:
    """تعیین review_status نهایی هنگام ثبت PlateRecognitionEvent."""
    if env is not None and env.review_required:
        return "NEEDS_REVIEW"
    if confidence is not None and float(confidence) < settings.PLATE_REVIEW_LOW_CONF:
        return "NEEDS_REVIEW"
    return "AUTO_OK"
