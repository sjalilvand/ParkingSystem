"""تست‌های D9 — تصمیم تأیید اصلاحیه توسط درخواست‌دهنده (پاک/بدون DB)."""
from app.modules.finance.service import self_approval_decision


def test_d9_warn_policy_allows_with_flag():
    allowed, flag = self_approval_decision("WARN", "user-1", "user-1")
    assert allowed is True
    assert flag is True


def test_d9_block_policy_denies_self():
    allowed, flag = self_approval_decision("BLOCK", "user-1", "user-1")
    assert allowed is False
    assert flag is True


def test_d9_block_policy_allows_others():
    allowed, flag = self_approval_decision("BLOCK", "user-1", "user-2")
    assert allowed is True
    assert flag is False


def test_d9_no_requester_is_not_self():
    allowed, flag = self_approval_decision("BLOCK", None, "user-1")
    assert allowed is True
    assert flag is False


def test_d9_missing_user_is_not_self():
    allowed, flag = self_approval_decision("BLOCK", "user-1", None)
    assert allowed is True
    assert flag is False


def test_d9_default_policy_is_warn():
    # policy خالی -> WARN (حفظ رفتار)
    allowed, flag = self_approval_decision("", "user-1", "user-1")
    assert allowed is True and flag is True


def test_d9_policy_case_insensitive():
    allowed, _ = self_approval_decision("block", "user-1", "user-1")
    assert allowed is False
