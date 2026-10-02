"""Wave4a unit - yard capacity decision (pure)."""
from app.capacity import yard_capacity_decision


def test_unlimited_when_none():
    assert yard_capacity_decision(None, 999) == (True, "OK")


def test_zero_means_unlimited():
    assert yard_capacity_decision(0, 10) == (True, "OK")


def test_below_capacity():
    assert yard_capacity_decision(5, 4) == (True, "OK")


def test_at_capacity():
    assert yard_capacity_decision(5, 5) == (False, "YARD_CAPACITY_FULL")


def test_over_capacity():
    assert yard_capacity_decision(5, 7) == (False, "YARD_CAPACITY_FULL")
