"""ماشین وضعیت تخلف (سند §۱۵) — توابع خالص قابل تست."""

VIOLATION_TRANSITIONS: dict[str, set[str]] = {
    "REGISTERED": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"CANCELLED"},
    "CANCELLED": set(),
}

APPEAL_RESULTS = {"ACCEPTED", "REJECTED"}


def can_transition(current: str | None, target: str) -> bool:
    return target in VIOLATION_TRANSITIONS.get((current or "").upper(), set())


def appeal_result_valid(result: str | None) -> bool:
    return (result or "").upper() in APPEAL_RESULTS


def voidable_charge_status(charge_status: str | None) -> bool:
    """ابطال مستند فقط برای شارژ تسویه‌نشده مجاز است (§۱۴).
    شارژ پرداخت‌شده باید از مسیر اصلاحیه/بازگشت وجه برود."""
    return (charge_status or "").upper() == "UNPAID"
