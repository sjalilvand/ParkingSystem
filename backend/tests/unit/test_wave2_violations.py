"""تست‌های موج ۲b — ماشین وضعیت تخلف (F19/F20)"""
import pytest

from app.modules.violations.service import (
    appeal_result_valid,
    can_transition,
    voidable_charge_status,
)


# ---------- انتقال‌های مجاز (§۱۵) ----------

def test_registered_can_confirm_or_cancel():
    assert can_transition("REGISTERED", "CONFIRMED")
    assert can_transition("REGISTERED", "CANCELLED")


def test_confirmed_can_only_cancel():
    assert can_transition("CONFIRMED", "CANCELLED")
    assert not can_transition("CONFIRMED", "CONFIRMED")


def test_cancelled_is_terminal():
    assert not can_transition("CANCELLED", "CONFIRMED")
    assert not can_transition("CANCELLED", "CANCELLED")


def test_unknown_current_denies_everything():
    assert not can_transition(None, "CONFIRMED")
    assert not can_transition("", "CANCELLED")
    assert not can_transition("WEIRD", "CONFIRMED")


def test_case_insensitive():
    assert can_transition("registered", "CONFIRMED")


# ---------- نتیجه اعتراض (F20) ----------

def test_appeal_results():
    assert appeal_result_valid("ACCEPTED")
    assert appeal_result_valid("rejected")
    assert not appeal_result_valid("MAYBE")
    assert not appeal_result_valid(None)
    assert not appeal_result_valid("")


# ---------- ابطال مستند شارژ (§۱۴) ----------

def test_only_unpaid_charge_voidable():
    assert voidable_charge_status("UNPAID")
    assert not voidable_charge_status("PAID")
    assert not voidable_charge_status("VOIDED")
    assert not voidable_charge_status(None)
