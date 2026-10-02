"""تست‌های ممیزی P0 — موج ۱ (بدون نیاز به دیتابیس)"""
import pytest

from app.core.config import Settings, validate_production_security
from app.modules.access_control.service import GateDecisionService
from app.modules.finance.models import Tariff
from app.modules.finance.service import calculate_amounts


# ---------- پیکربندی امن production ----------

def test_production_with_default_secrets_fails_fast():
    s = Settings(APP_ENV="production")
    with pytest.raises(RuntimeError):
        validate_production_security(s)


def test_production_with_strong_secrets_passes():
    s = Settings(
        APP_ENV="production",
        JWT_SECRET_KEY="a" * 40,
        APP_SECRET_KEY="b" * 40,
        GATE_API_KEY="c" * 24,
        DEFAULT_ADMIN_PASSWORD="Str0ng!Pass",
    )
    validate_production_security(s)  # نباید خطا بدهد


def test_development_allows_defaults():
    s = Settings(APP_ENV="development")
    validate_production_security(s)


# ---------- تصمیم راهبند ----------

def test_barrier_action_mapping():
    assert GateDecisionService.barrier_action_for("ALLOW") == "OPEN"
    assert GateDecisionService.barrier_action_for("ALLOW_WITH_WARNING") == "OPEN"
    assert GateDecisionService.barrier_action_for("OFFLINE_ALLOW") == "OPEN"
    assert GateDecisionService.barrier_action_for("DENY") == "KEEP_CLOSED"
    assert GateDecisionService.barrier_action_for("UNKNOWN_PLATE") == "KEEP_CLOSED"


# ---------- مرزهای محاسبه تعرفه (سند بخش ۲۱ — رفتار فعلی: گردکردن رو به بالا) ----------
# توجه: قاعده گردکردن و سقف‌ها طبق سند بخش ۲۳ نیازمند تصویب نهایی هستند.

def _tariff(**kw) -> Tariff:
    base = dict(title="audit-t", free_minutes=0, hourly_amount=150_000, daily_max_amount=None)
    base.update(kw)
    return Tariff(**base)


def test_zero_duration_is_free():
    assert calculate_amounts(_tariff(), 0)["final"] == 0


def test_negative_duration_clamped():
    assert calculate_amounts(_tariff(), -100)["final"] == 0


def test_no_tariff_warning():
    r = calculate_amounts(None, 3600)
    assert r["final"] == 0 and "NO_ACTIVE_TARIFF" in r["warnings"]


def test_free_minutes_cover_exactly():
    r = calculate_amounts(_tariff(free_minutes=15), 15 * 60)
    assert r["final"] == 0


def test_90_minutes_rounds_up_to_2_hours():
    assert calculate_amounts(_tariff(), 90 * 60)["final"] == 2 * 150_000


def test_91_minutes_rounds_up_to_2_hours():
    assert calculate_amounts(_tariff(), 91 * 60)["final"] == 2 * 150_000


def test_150_minutes_3_hours():
    assert calculate_amounts(_tariff(), 150 * 60)["final"] == 3 * 150_000


def test_151_minutes_3_hours():
    assert calculate_amounts(_tariff(), 151 * 60)["final"] == 3 * 150_000


def test_daily_cap_applied_multiday():
    t = _tariff(hourly_amount=150_000, daily_max_amount=500_000)
    r = calculate_amounts(t, 30 * 3600)  # 30 ساعت → 4.5M > سقف 2 روز = 1.0M
    assert r["final"] == 500_000 * 2
    assert "DAILY_CAP_APPLIED" in r["warnings"]


def test_daily_cap_not_applied_when_below():
    t = _tariff(hourly_amount=150_000, daily_max_amount=500_000)
    r = calculate_amounts(t, 2 * 3600)
    assert r["final"] == 300_000
