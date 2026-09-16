from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.modules.vehicles.service import permit_entries_available, permit_gate_allowed, permit_time_valid


def _permit(**kw):
    base = dict(valid_from=None, valid_until=None, allowed_days=None, allowed_from_time=None,
                allowed_until_time=None, max_entries=None, used_entries=0, allowed_gate_ids=None)
    base.update(kw)
    return SimpleNamespace(**base)


NOW = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)


def test_valid_permit():
    ok, reason = permit_time_valid(_permit(), NOW)
    assert ok and reason == "OK"


def test_expired():
    ok, reason = permit_time_valid(_permit(valid_until=NOW - timedelta(hours=1)), NOW)
    assert not ok and reason == "PERMIT_EXPIRED"


def test_not_started():
    ok, reason = permit_time_valid(_permit(valid_from=NOW + timedelta(hours=1)), NOW)
    assert not ok and reason == "PERMIT_NOT_STARTED"


def test_day_not_allowed():
    ok, reason = permit_time_valid(_permit(allowed_days="[5, 6]"), NOW)
    assert not ok and reason == "PERMIT_DAY_NOT_ALLOWED"


def test_time_window_ok():
    ok, _ = permit_time_valid(_permit(allowed_from_time="08:00", allowed_until_time="12:00"), NOW)
    assert ok


def test_time_window_fail():
    ok, reason = permit_time_valid(_permit(allowed_from_time="14:00", allowed_until_time="18:00"), NOW)
    assert not ok and reason == "PERMIT_TIME_NOT_ALLOWED"


def test_overnight_window():
    ok, _ = permit_time_valid(_permit(allowed_from_time="22:00", allowed_until_time="06:00"), NOW.replace(hour=23))
    assert ok


def test_max_entries():
    ok, reason = permit_entries_available(_permit(max_entries=2, used_entries=2))
    assert not ok and reason == "PERMIT_MAX_ENTRIES_REACHED"


def test_gate_allowed():
    assert permit_gate_allowed(_permit(allowed_gate_ids='["g1"]'), "g1") is True
    assert permit_gate_allowed(_permit(allowed_gate_ids='["g1"]'), "g2") is False
    assert permit_gate_allowed(_permit(), "g2") is True