"""تست‌های D10 — خلاصه مالی با تکلیف شارژ VOIDED (پاک/بدون DB)."""
from types import SimpleNamespace

from app.modules.finance.service import summarize_charges_for_report


def _charge(status="UNPAID", amount=10000, paid_amount=0):
    return SimpleNamespace(status=status, amount=amount, paid_amount=paid_amount)


def test_d10_separate_mode_voided_excluded_from_active_totals():
    rows = [
        _charge("UNPAID", 10000),
        _charge("PAID", 20000, paid_amount=20000),
        _charge("VOIDED", 50000),
    ]
    r = summarize_charges_for_report(rows, "SEPARATE")
    assert r["voided_mode"] == "SEPARATE"
    assert r["active"]["unpaid_total"] == 10000
    assert r["active"]["paid_total"] == 20000
    assert r["active"]["grand_total"] == 30000
    assert r["voided"]["total"] == 50000
    assert r["voided"]["count"] == 1


def test_d10_exclude_mode_voided_removed_entirely():
    rows = [
        _charge("UNPAID", 10000),
        _charge("VOIDED", 50000),
    ]
    r = summarize_charges_for_report(rows, "EXCLUDE")
    assert r["voided_mode"] == "EXCLUDE"
    assert r["active"]["grand_total"] == 10000
    assert r["voided"]["total"] == 0
    assert r["voided"]["count"] == 0


def test_d10_default_mode_is_separate():
    rows = [_charge("VOIDED", 50000)]
    r = summarize_charges_for_report(rows, None)
    assert r["voided_mode"] == "SEPARATE"
    assert r["voided"]["total"] == 50000


def test_d10_invalid_mode_falls_back_to_separate():
    rows = [_charge("VOIDED", 50000)]
    r = summarize_charges_for_report(rows, "WEIRD")
    assert r["voided_mode"] == "SEPARATE"


def test_d10_partially_paid_counts_outstanding():
    rows = [_charge("UNPAID", 20000, paid_amount=5000)]
    r = summarize_charges_for_report(rows, "SEPARATE")
    assert r["active"]["unpaid_total"] == 15000
    assert r["active"]["unpaid_count"] == 1


def test_d10_zero_outstanding_treated_as_paid():
    rows = [_charge("UNPAID", 20000, paid_amount=20000)]
    r = summarize_charges_for_report(rows, "SEPARATE")
    assert r["active"]["paid_total"] == 20000
    assert r["active"]["unpaid_total"] == 0


def test_d10_empty_rows():
    r = summarize_charges_for_report([], "SEPARATE")
    assert r["active"]["grand_total"] == 0
    assert r["voided"]["total"] == 0
