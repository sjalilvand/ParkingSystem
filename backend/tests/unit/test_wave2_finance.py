"""تست‌های موج ۲a — مالی: تخصیص پرداخت جزئی (F16) و وضعیت تعرفه (F8)"""
from types import SimpleNamespace

from app.modules.finance.service import (
    allocate_payment_amounts,
    calculate_amounts,
    charge_outstanding,
    initial_tariff_status,
)


class C(SimpleNamespace):
    pass


def _charge(amount, paid=0, ctype="PARKING", id="c1"):
    return C(id=id, amount=amount, paid_amount=paid, charge_type=ctype, status="UNPAID")


# ---------- F16: outstanding ----------

def test_outstanding_full_debt():
    assert charge_outstanding(_charge(100_000)) == 100_000


def test_outstanding_after_partial():
    assert charge_outstanding(_charge(100_000, paid=40_000)) == 60_000


def test_outstanding_never_negative():
    assert charge_outstanding(_charge(50_000, paid=80_000)) == 0


# ---------- F16: allocation ----------

def test_allocation_full_single_charge():
    cs = [_charge(100_000)]
    allocs, rem = allocate_payment_amounts(cs, 100_000)
    assert [(c.id, a) for c, a in allocs] == [("c1", 100_000)]
    assert rem == 0


def test_allocation_partial_single_charge():
    cs = [_charge(100_000)]
    allocs, rem = allocate_payment_amounts(cs, 40_000)
    assert [(c.id, a) for c, a in allocs] == [("c1", 40_000)]
    assert rem == 0  # شارژ همچنان 60k بدهکار است — دوباره شمارش نمی‌شود


def test_allocation_spans_multiple_charges_in_order():
    cs = [_charge(50_000, id="a"), _charge(70_000, id="b", ctype="VIOLATION")]
    allocs, rem = allocate_payment_amounts(cs, 100_000)
    assert [(c.id, a) for c, a in allocs] == [("a", 50_000), ("b", 50_000)]
    assert rem == 0


def test_allocation_overpay_leaves_credit():
    cs = [_charge(50_000)]
    allocs, rem = allocate_payment_amounts(cs, 80_000)
    assert allocs[0][1] == 50_000 and rem == 30_000


def test_allocation_skips_settled_charge():
    cs = [_charge(50_000, paid=50_000), _charge(30_000, id="b")]
    allocs, rem = allocate_payment_amounts(cs, 30_000)
    assert [(c.id, a) for c, a in allocs] == [("b", 30_000)]
    assert rem == 0


def test_allocation_zero_amount():
    allocs, rem = allocate_payment_amounts([_charge(50_000)], 0)
    assert allocs == [] and rem == 0


# ---------- F8: tariff lifecycle ----------

def test_tariff_draft_when_approval_required():
    assert initial_tariff_status(True) == "DRAFT"


def test_tariff_active_without_approval():
    assert initial_tariff_status(False) == "ACTIVE"


# ---------- مرز §۲۳ (رفتار فعلی، تصمیم D5 معلق) ----------

def test_exactly_24h():
    t = SimpleNamespace(free_minutes=0, hourly_amount=150_000, daily_max_amount=None)
    assert calculate_amounts(t, 24 * 3600)["final"] == 24 * 150_000


def test_multiday_crossing_midnight():
    t = SimpleNamespace(free_minutes=0, hourly_amount=150_000, daily_max_amount=500_000)
    r = calculate_amounts(t, 26 * 3600)
    assert r["final"] == 500_000 * 2  # سقف ۲ روز
