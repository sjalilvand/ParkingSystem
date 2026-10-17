"""تست‌های D1/D7 — خواندن سیاست‌های زمان-اجرا از app_settings با FakeDB (unit)."""
import pytest

from app.core.runtime_settings import (
    get_policy_setting,
    resolve_exit_policy,
    resolve_tariff_policy,
    tariff_calc_kwargs,
)


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class FakeDB:
    """حداقل AsyncSession موردنیاز get_policy_setting — فقط execute."""

    def __init__(self, value=None, raise_error=False):
        self._value = value
        self._raise = raise_error

    async def execute(self, stmt):
        if self._raise:
            raise RuntimeError("db unavailable")
        return _FakeResult(SimpleRow(self._value))


class SimpleRow:
    def __init__(self, value):
        self.value = value


# ---------------- D1: سیاست خروج ----------------

@pytest.mark.asyncio
async def test_d1_default_warn_from_env():
    # بدون رکورد app_settings -> env پیش‌فرض WARN
    assert await resolve_exit_policy(FakeDB(None)) == "WARN"


@pytest.mark.asyncio
async def test_d1_deny_from_app_settings():
    db = FakeDB({"EXIT_UNPAID_POLICY": "DENY"})
    assert await resolve_exit_policy(db) == "DENY"


@pytest.mark.asyncio
async def test_d1_allow_from_app_settings():
    db = FakeDB({"EXIT_UNPAID_POLICY": "ALLOW"})
    assert await resolve_exit_policy(db) == "ALLOW"


@pytest.mark.asyncio
async def test_d1_invalid_value_falls_back_to_warn():
    db = FakeDB({"EXIT_UNPAID_POLICY": "FOO"})
    assert await resolve_exit_policy(db) == "WARN"


@pytest.mark.asyncio
async def test_d1_db_error_falls_back_to_env():
    assert await resolve_exit_policy(FakeDB(None, raise_error=True)) == "WARN"


# ---------------- D2/D3/D4/D7: سیاست تعرفه ----------------

@pytest.mark.asyncio
async def test_tariff_policy_defaults_from_env():
    p = await resolve_tariff_policy(FakeDB(None))
    assert p["rounding"] == "HOUR_UP"
    assert p["day_definition"] == "24H"
    assert p["night_enabled"] is False
    assert p["night_start_hour"] == 22 and p["night_end_hour"] == 6
    assert p["min_charge_amount"] == 0
    assert p["exit_grace_minutes"] == 20


@pytest.mark.asyncio
async def test_tariff_policy_app_settings_lowercase_aliases():
    # قالب قدیمی config_admin (کلیدهای lowercase) باید خوانده شود
    db = FakeDB({
        "rounding": "MINUTE",
        "day_definition": "CALENDAR",
        "night_enabled": True,
        "night_start_hour": 23,
        "night_end_hour": 5,
        "min_charge_amount": 10000,
        "exit_grace_minutes": 45,
    })
    p = await resolve_tariff_policy(db)
    assert p["rounding"] == "MINUTE"
    assert p["day_definition"] == "CALENDAR"
    assert p["night_enabled"] is True
    assert p["night_start_hour"] == 23 and p["night_end_hour"] == 5
    assert p["min_charge_amount"] == 10000
    assert p["exit_grace_minutes"] == 45


@pytest.mark.asyncio
async def test_tariff_policy_invalid_values_sanitized():
    db = FakeDB({
        "rounding": "WEIRD",
        "day_definition": "WEEK",
        "min_charge_amount": "not-a-number",  # cast ناموفق -> env fallback
    })
    p = await resolve_tariff_policy(db)
    assert p["rounding"] == "HOUR_UP"
    assert p["day_definition"] == "24H"
    assert p["min_charge_amount"] == 0


@pytest.mark.asyncio
async def test_tariff_policy_bool_from_string():
    db = FakeDB({"night_enabled": "false"})
    p = await resolve_tariff_policy(db)
    assert p["night_enabled"] is False


def test_tariff_calc_kwargs_excludes_grace():
    policy = {"rounding": "MINUTE", "day_definition": "24H", "night_enabled": False,
              "night_start_hour": 22, "night_end_hour": 6, "min_charge_amount": 0,
              "exit_grace_minutes": 20}
    kw = tariff_calc_kwargs(policy)
    assert "exit_grace_minutes" not in kw
    assert kw["rounding"] == "MINUTE"


@pytest.mark.asyncio
async def test_get_policy_setting_env_fallback():
    v = await get_policy_setting(FakeDB(None), "x_group", "EXIT_UNPAID_POLICY")
    assert v == "WARN"
