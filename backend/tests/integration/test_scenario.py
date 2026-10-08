"""Wave6 — سناریوساز: purge + setup-default + قوانین."""
from helpers import GATE_HEADERS, api_client, auth, login, run


def test_purge_setup_default_and_gate():
    async def go():
        async with api_client() as ac:
            tok = await login(ac, "admin", "Admin@1234")
            h = auth(tok)

            # ۱) پاکسازی همه (به‌جز ادمین)
            p = await ac.post("/api/v1/scenario/purge", headers=h, json={"categories": []})
            assert p.status_code == 200, p.text

            # ۲) سناریوی پیش‌فرض
            s = await ac.post("/api/v1/scenario/setup-default", headers=h)
            assert s.status_code == 200, s.text
            js = s.json()
            assert len(js["residents"]) == 2 and len(js["vehicles"]) == 8, js
            assert js["rules_created"] == 3

            # ۳) خلاصه
            sm = (await ac.get("/api/v1/scenario/summary", headers=h)).json()
            assert sm["units"] >= 2 and sm["residents"] >= 2 and sm["vehicles"] >= 8, sm

            # ۴) ورود خودروی اول ساکن ۱ — DIAGNOSTIC: بررسی داده قبل از تصمیم
            from sqlalchemy import select as _sel
            from app.db.session import AsyncSessionLocal as _ASL
            from app.modules.vehicles.models import Vehicle as _V
            async with _ASL() as _db:
                _vs = (await _db.execute(_sel(_V))).scalars().all()
                _norms = [v.plate_normalized for v in _vs]
            print(f"[DIAG] vehicles in DB after setup: {len(_vs)} -> {_norms}")
            assert "12B345IR11" in _norms, f"setup-default did not create vehicle! norms={_norms}"
            g1 = await ac.post("/api/v1/gate/access/check", headers=GATE_HEADERS, json={
                "gate_code": "GATE-IN-01", "direction": "IN",
                "plate_raw": "12ب345ایران11", "source_event_id": "sc-1"})
            j1 = g1.json()
            print(f"[DIAG] decision={j1['decision']} reason={j1.get('decision_reason')}")
            assert j1["decision"] in ("ALLOW", "ALLOW_WITH_WARNING"), j1

            # ۵) غریبه → بدون قانون منتشرشده = UNKNOWN_PLATE
            g2 = await ac.post("/api/v1/gate/access/check", headers=GATE_HEADERS, json={
                "gate_code": "GATE-IN-01", "direction": "IN",
                "plate_raw": "77ط123ایران77", "source_event_id": "sc-2"})
            assert g2.json()["decision"] == "UNKNOWN_PLATE", g2.json()

            # ۶) انتشار قانون «متقاضی محوطه» → dry-run با driver_request=YARD باید برسد به RULE_YARD_REQUEST
            rules = (await ac.get("/api/v1/rules", headers=h)).json()
            rule_yard = [r for r in rules if r["name"] == "متقاضی محوطه → بررسی اپراتور"][0]
            pub = await ac.post(f"/api/v1/rules/{rule_yard['id']}/publish", headers=h, json={"reason": "scenario"})
            assert pub.status_code == 200
            g3 = await ac.post("/api/v1/gate/access/check", headers=GATE_HEADERS, json={
                "gate_code": "GATE-IN-01", "direction": "IN",
                "plate_raw": "77ط123ایران77", "source_event_id": "sc-3",
                "driver_request": "YARD"})
            j3 = g3.json()
            assert j3["decision"] == "ALLOW_WITH_WARNING", j3
            assert j3["decision_reason"] == "RULE_YARD_REQUEST", j3
    run(go())
