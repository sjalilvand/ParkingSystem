from types import SimpleNamespace

from app.modules.finance.service import calculate_amounts


def _tariff(**kw):
    base = dict(free_minutes=0, hourly_amount=10000, daily_max_amount=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_no_tariff_zero_with_warning():
    r = calculate_amounts(None, 7200)
    assert r["final"] == 0 and "NO_ACTIVE_TARIFF" in r["warnings"]


def test_within_free_minutes():
    r = calculate_amounts(_tariff(free_minutes=15), 600)
    assert r["final"] == 0 and r["warnings"] == []


def test_one_hour_ceil():
    r = calculate_amounts(_tariff(), 60)  # 1s billable -> ceil -> 1h
    assert r["base"] == 10000 and r["final"] == 10000


def test_two_hours():
    r = calculate_amounts(_tariff(), 5400)  # 1.5h -> ceil 2h
    assert r["final"] == 20000


def test_daily_cap_applied():
    r = calculate_amounts(_tariff(daily_max_amount=15000), 7200)
    assert r["final"] == 15000 and "DAILY_CAP_APPLIED" in r["warnings"]


def test_zero_duration():
    r = calculate_amounts(_tariff(), 0)
    assert r["final"] == 0