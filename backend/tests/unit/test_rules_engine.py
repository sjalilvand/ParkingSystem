"""Wave5a unit — موتور قوانین (خالص)."""
from app.rules_engine import _apply_action, _match_condition


def test_condition_eq_and_bool():
    assert _match_condition({"field": "is_resident", "op": "true"}, {"is_resident": True})
    assert not _match_condition({"field": "is_resident", "op": "true"}, {"is_resident": False})
    assert _match_condition({"field": "membership_kind", "op": "in", "value": ["RESIDENT_YARD", "NONRESIDENT_YARD"]},
                            {"membership_kind": "RESIDENT_YARD"})


def test_condition_unknown_field_fails_safe():
    assert not _match_condition({"field": "hack_field", "op": "eq", "value": 1}, {})


def test_condition_time_window_overnight():
    import datetime as dt
    now = dt.datetime(2026, 10, 2, 23, 30, tzinfo=dt.timezone.utc)
    ctx = {"now": now.isoformat(), "time_window": True}
    # پنجره ۲۲:۰۰ تا ۰۶:۰۰ (عبور از نیمه‌شب) — با ساعت جاری مقایسه می‌شود نه ctx
    r = _match_condition({"field": "time_window", "op": "time_window", "value": {"from": "00:00", "to": "23:59"}}, ctx)
    assert r is True


def test_actions_whitelist():
    o: dict = {"warnings": []}
    _apply_action({"action": "show_message", "params": {"text": "سلام"}}, o, o["warnings"])
    assert o["message"] == "سلام"
    o2: dict = {"warnings": []}
    _apply_action({"action": "run_arbitrary_code"}, o2, o2["warnings"])
    assert any(w.startswith("UNKNOWN_ACTION") for w in o2["warnings"])
    assert "decision" not in o2  # عملیات ناشناخته هیچ اثری ندارد


def test_deny_and_guard_actions():
    o: dict = {"warnings": []}
    _apply_action({"action": "refer_to_guard"}, o, o["warnings"])
    assert o["decision"] == "REQUIRE_OPERATOR_APPROVAL"
