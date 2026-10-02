"""Wave5a integration — قوانین واقعاً به موتور ورود متصل‌اند."""
from sqlalchemy import select

from helpers import GATE_HEADERS, api_client, auth, login, run


def test_rule_publish_and_live_effect_and_simulate():
    async def go():
        from app.db.session import AsyncSessionLocal
        from app.modules.access_control.models import ParkingSession
        async with api_client() as ac:
            tok = await login(ac, "admin", "Admin@1234")
            h = auth(tok)
            # ساخت قانون: پلاک ناشناس با درخواست YARD → تأیید با هشدار + انتخاب راننده
            r = await ac.post("/api/v1/rules", headers=h, json={
                "name": "پذیرش محوطه برای غیرساکن", "direction": "IN", "priority": 10,
                "condition_mode": "ALL",
                "conditions": [
                    {"field": "membership_kind", "op": "eq", "value": None},
                    {"field": "driver_request", "op": "eq", "value": "YARD"},
                ],
                "actions": [
                    {"action": "allow_with_warning", "params": {"reason": "RULE_YARD_REQUEST"}},
                    {"action": "require_driver_selection"},
                    {"action": "show_message", "params": {"text": "لطفاً نوع استفاده را انتخاب کنید"}},
                ]})
            assert r.status_code == 200, r.text
            rid = r.json()["id"]
            assert r.json()["status"] == "DRAFT"

            # DRAFT: اثری ندارد → همان UNKNOWN_PLATE
            p1 = await ac.post("/api/v1/gate/access/check", headers=GATE_HEADERS, json={
                "gate_code": "GATE-IN-01", "direction": "IN",
                "plate_raw": "99Z999IR11", "source_event_id": "sim-draft",
                "driver_request": "YARD"})
            j1 = p1.json()
            assert j1["decision"] == "UNKNOWN_PLATE", j1

            # انتشار
            pub = await ac.post(f"/api/v1/rules/{rid}/publish", headers=h, json={"reason": "test"})
            assert pub.status_code == 200, pub.text

            # حالا قانون زنده است (dry-run check)
            p2 = await ac.post("/api/v1/gate/access/check", headers=GATE_HEADERS, json={
                "gate_code": "GATE-IN-01", "direction": "IN",
                "plate_raw": "99Z999IR11", "source_event_id": "sim-live",
                "driver_request": "YARD"})
            j2 = p2.json()
            assert j2["decision"] == "ALLOW_WITH_WARNING", j2
            assert j2["decision_reason"] == "RULE_YARD_REQUEST", j2
            assert j2.get("require_driver_selection") is True
            assert j2.get("message") == "لطفاً نوع استفاده را انتخاب کنید"
            assert j2["rule_trace"]["rule_id"] == rid

            # بدون driver_request → قانون نمی‌خورد → UNKNOWN_PLATE
            p3 = await ac.post("/api/v1/gate/access/check", headers=GATE_HEADERS, json={
                "gate_code": "GATE-IN-01", "direction": "IN",
                "plate_raw": "99Z999IR11", "source_event_id": "sim-nodrv"})
            assert p3.json()["decision"] == "UNKNOWN_PLATE"

            # غیرفعال‌سازی → اثر از بین می‌رود
            d = await ac.post(f"/api/v1/rules/{rid}/disable", headers=h)
            assert d.status_code == 200
            p4 = await ac.post("/api/v1/gate/access/check", headers=GATE_HEADERS, json={
                "gate_code": "GATE-IN-01", "direction": "IN",
                "plate_raw": "99Z999IR11", "source_event_id": "sim-off",
                "driver_request": "YARD"})
            assert p4.json()["decision"] == "UNKNOWN_PLATE"

            # dry-run هیچ نشستی نساخته باشد
            async with AsyncSessionLocal() as db:
                n = (await db.execute(select(ParkingSession).where(
                    ParkingSession.plate_normalized == "99Z999IR11"))).scalars().all()
                assert len(n) == 0

            # settings + history
            s = await ac.put("/api/v1/app-settings/tariff_policy", headers=h, json={
                "value": {"free_minutes": 60}, "reason": "test-change"})
            assert s.status_code == 200, s.text
            g = (await ac.get("/api/v1/app-settings/tariff_policy", headers=h)).json()
            assert g["is_default"] is False and g["value"]["free_minutes"] == 60
            hist = (await ac.get("/api/v1/app-settings/tariff_policy/history", headers=h)).json()
            assert len(hist) >= 1 and hist[0]["reason"] == "test-change"

            # گروه‌های seed شده
            gr = (await ac.get("/api/v1/vehicle-groups", headers=h)).json()
            assert {x["code"] for x in gr} >= {"PRIMARY_COVERED", "SECONDARY_COVERED",
                                               "RESIDENT_YARD", "NONRESIDENT_YARD", "SPECIAL_PERMIT"}

            # box settings
            b = (await ac.get("/api/v1/box-settings/IN", headers=h)).json()
            assert b["side"] == "IN" and any(x["key"] == "yard_request" for x in b["buttons"])

            # مجوز محدود: 403 روی تنظیمات
            tok2 = await login(ac, "op1", "Op@123456")
            r403 = await ac.put("/api/v1/app-settings/tariff_policy", headers=auth(tok2), json={"value": {}})
            assert r403.status_code == 403
    run(go())
