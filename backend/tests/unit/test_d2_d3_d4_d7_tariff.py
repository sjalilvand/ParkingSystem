"""تست‌های D2/D3/D4/D7 — سیاست‌های محاسبه تعرفه (unit، بدون DB).

پیش‌فرض‌ها دقیقاً رفتار قبلی را بازتولید می‌کنند (سازگاری کامل — test_tariff قدیمی).
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.modules.finance.service import calculate_amounts, night_overlap_seconds

TEHRAN_OFFSET = timezone(timedelta(hours=3, minutes=30))


def _tariff(**kw):
    base = dict(free_minutes=0, hourly_amount=10000, daily_max_amount=None,
                night_amount=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _tehran(h, m=0):
    """ساعت محلی تهران در ۱۴۰۵/۰۱/۰۱ (2026-03-21)."""
    return datetime(2026, 3, 21, h, m, tzinfo=TEHRAN_OFFSET)


# ---------------- سازگاری رفتار قبلی (بدون پارامتر) ----------------

def test_backward_compat_ceil_hour():
    r = calculate_amounts(_tariff(), 5400)  # 1.5h -> ceil 2h
    assert r["final"] == 20000
    assert r["warnings"] == []


def test_backward_compat_daily_cap():
    r = calculate_amounts(_tariff(daily_max_amount=15000), 7200)
    assert r["final"] == 15000 and "DAILY_CAP_APPLIED" in r["warnings"]


# ---------------- D2: قاعده گرد کردن ----------------

def test_d2_hour_up_is_default():
    # 90 دقیقه -> ساعتی رو به بالا = 2 ساعت
    r = calculate_amounts(_tariff(), 5400, rounding="HOUR_UP")
    assert r["final"] == 20000


def test_d2_minute_rounding():
    # 90 دقیقه -> دقیقه‌ای = 1.5 ساعت
    r = calculate_amounts(_tariff(), 5400, rounding="MINUTE")
    assert r["final"] == 15000


def test_d2_minute_rounding_partial_minute():
    # 30 دقیقه و 1 ثانیه -> دقیقه‌ای = 30.0166 دقیقه * نرخ
    r = calculate_amounts(_tariff(), 1801, rounding="MINUTE")
    assert r["final"] == int(round((1801 / 3600) * 10000))


# ---------------- D3: سقف روزانه در چندروزه ----------------

def test_d3_24h_definition_ceil():
    # 3 ساعت توقف: 24H -> ceil(3h/24h) = 1 روز -> سقف = daily_max*1
    t = _tariff(daily_max_amount=12000)
    r = calculate_amounts(t, 3 * 3600, day_definition="24H")
    assert r["final"] == 12000 and "DAILY_CAP_APPLIED" in r["warnings"]


def test_d3_calendar_definition_crosses_midnight():
    # ورود 23:00 تهران + 3 ساعت (عبور از نیمه‌شب) -> CALENDAR = 2 روز -> سقف*2
    t = _tariff(daily_max_amount=12000)
    r = calculate_amounts(t, 3 * 3600, day_definition="CALENDAR",
                          entry_at=_tehran(23, 0))
    assert r["final"] == 24000 and "DAILY_CAP_APPLIED" in r["warnings"]


def test_d3_calendar_same_day_unchanged():
    # ورود 10:00 + 3 ساعت -> همان روز = 1 روز -> سقف*1
    t = _tariff(daily_max_amount=12000)
    r = calculate_amounts(t, 3 * 3600, day_definition="CALENDAR",
                          entry_at=_tehran(10, 0))
    assert r["final"] == 12000


def test_d3_calendar_without_entry_falls_back():
    # CALENDAR بدون entry_at -> fallback به 24H + هشدار
    t = _tariff(daily_max_amount=12000)
    r = calculate_amounts(t, 3 * 3600, day_definition="CALENDAR", entry_at=None)
    assert r["final"] == 12000 and "DAY_DEFINITION_FALLBACK_24H" in r["warnings"]


# ---------------- D4: تعرفه شب (F11) ----------------

def test_d4_night_overlap_full_window():
    # 21:00 -> 07:00 (10 ساعت): پنجره شب 22->06 = 8 ساعت
    s = night_overlap_seconds(_tehran(21, 0), 10 * 3600)
    assert s == 8 * 3600


def test_d4_night_overlap_none():
    # 07:00 -> 21:00 (14 ساعت روز): هیچ همپوشانی شب
    s = night_overlap_seconds(_tehran(7, 0), 14 * 3600)
    assert s == 0


def test_d4_night_calculation():
    # 10 ساعت توقف از 21:00: شب 8h*5000 + روز 2h*10000 = 60000
    t = _tariff(hourly_amount=10000, night_amount=5000)
    r = calculate_amounts(t, 10 * 3600, entry_at=_tehran(21, 0),
                          night_enabled=True, night_start_hour=22, night_end_hour=6)
    assert r["final"] == 60000
    assert "NIGHT_TARIFF_APPLIED" in r["warnings"]


def test_d4_night_disabled_by_default():
    # همان ورودی بدون فعال‌سازی شب -> رفتار قبلی: 10h -> ceil = 10*10000
    t = _tariff(hourly_amount=10000, night_amount=5000)
    r = calculate_amounts(t, 10 * 3600, entry_at=_tehran(21, 0))
    assert r["final"] == 100000 and "NIGHT_TARIFF_APPLIED" not in r["warnings"]


def test_d4_night_enabled_without_entry_time_skips():
    t = _tariff(hourly_amount=10000, night_amount=5000)
    r = calculate_amounts(t, 10 * 3600, night_enabled=True)
    assert r["final"] == 100000 and "NIGHT_SKIPPED_NO_ENTRY_TIME" in r["warnings"]


def test_d4_night_partial_hour_up():
    # 05:00 -> 06:30: شب 1h (05->06) + روز 30min -> HOUR_UP: 1*5000 + 1*10000
    t = _tariff(hourly_amount=10000, night_amount=5000)
    r = calculate_amounts(t, 90 * 60, entry_at=_tehran(5, 0),
                          night_enabled=True, night_start_hour=22, night_end_hour=6)
    assert r["final"] == 15000


def test_d4_night_plus_daily_cap():
    # شب 8h*5000=40000 + روز 2h*10000=20000 = 60000؛ سقف 2 روزه (عبور نیمه‌شب) = 24000*2
    t = _tariff(hourly_amount=10000, night_amount=5000, daily_max_amount=24000)
    r = calculate_amounts(t, 10 * 3600, entry_at=_tehran(21, 0),
                          night_enabled=True, night_start_hour=22, night_end_hour=6,
                          day_definition="CALENDAR")
    assert r["final"] == 48000 and "DAILY_CAP_APPLIED" in r["warnings"]


# ---------------- D7: حداقل مبلغ شارژ ----------------

def test_d7_min_amount_applied():
    # 30 دقیقه ساعتی 1000 = 1000؛ حداقل 5000 -> 5000
    t = _tariff(hourly_amount=1000)
    r = calculate_amounts(t, 1800, min_charge_amount=5000)
    assert r["final"] == 5000 and "MIN_AMOUNT_APPLIED" in r["warnings"]


def test_d7_min_amount_not_below_zero():
    # داخل بازه رایگان -> صفر (حداقل اعمال نمی‌شود)
    t = _tariff(hourly_amount=1000, free_minutes=60)
    r = calculate_amounts(t, 1800, min_charge_amount=5000)
    assert r["final"] == 0 and "MIN_AMOUNT_APPLIED" not in r["warnings"]


def test_d7_min_amount_above_computed():
    # مبلغ محاسبه‌شده بالاتر از حداقل -> بدون تغییر
    t = _tariff(hourly_amount=10000)
    r = calculate_amounts(t, 7200, min_charge_amount=5000)
    assert r["final"] == 20000 and "MIN_AMOUNT_APPLIED" not in r["warnings"]


def test_d7_min_amount_disabled_by_default():
    t = _tariff(hourly_amount=1000)
    r = calculate_amounts(t, 1800)
    assert r["final"] == 1000 and "MIN_AMOUNT_APPLIED" not in r["warnings"]
