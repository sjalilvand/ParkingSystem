"""تست‌های D6 — کاتالوگ مجوزها و نگاشت نقش‌ها (داده‌ای، بدون DB)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.seed_rbac import MATRIX, ROLES


def test_d6_finance_permissions_in_catalog():
    # روتر مالی به finance.view/pay/manage وابسته است — باید در کاتالوگ باشد
    assert set(MATRIX["finance"]) == {"view", "pay", "manage"}


def test_d6_settings_rules_groups_in_catalog():
    assert set(MATRIX["settings"]) == {"view", "edit", "publish"}
    assert set(MATRIX["rules"]) == {"view", "edit", "publish"}
    assert set(MATRIX["groups"]) == {"view", "edit"}


def test_d6_guard_has_finance_pay():
    # نگهبان گیت باید بدهی را ببیند و پرداخت نقدی ثبت کند
    assert "finance.view" in ROLES["GUARD_IN"]["perms"]
    assert "finance.pay" in ROLES["GUARD_IN"]["perms"]


def test_d6_observer_roles_have_finance_view():
    # صفحه بدهی‌ها به finance.view وابسته است — نقش‌های مشاهده‌گر هم داشته باشند
    assert "finance.view" in ROLES["BUILDING_OBSERVER"]["perms"]
    assert "finance.view" in ROLES["PLAN_MANAGER"]["perms"]
    assert "finance.view" in ROLES["YARD_MANAGER"]["perms"]


def test_d6_all_role_perms_exist_in_matrix():
    # هر کد مجوز تخصیص‌یافته باید در کاتالوگ MATRIX تعریف شده باشد
    catalog = {f"{mod}.{act}" for mod, acts in MATRIX.items() for act in acts}
    for code, spec in ROLES.items():
        perms = spec["perms"]
        if perms is None:  # ADMIN = همه
            continue
        missing = set(perms) - catalog
        assert not missing, f"role {code} has unknown perms: {missing}"


def test_d6_admin_has_all():
    assert ROLES["ADMIN"]["perms"] is None


def test_d6_finance_manage_stays_admin_only():
    # finance.manage فقط برای ADMIN (perms=None) — هیچ نقش دیگری نداشته باشد
    for code, spec in ROLES.items():
        if spec["perms"] is None:
            continue
        assert "finance.manage" not in spec["perms"], f"{code} نباید finance.manage داشته باشد"
