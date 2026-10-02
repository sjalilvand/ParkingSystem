"""Wave5i — ثبت دسته‌ای محوطه + ظرفیت از تنظیمات طراح (زنجیره تا موتور گیت)."""
from helpers import GATE_HEADERS, api_client, auth, login, run


def test_yard_bulk_delete_and_capacity_via_setting():
    async def go():
        from sqlalchemy import delete, text
        from app.db.session import AsyncSessionLocal
        from app.modules.access_control.models import ParkingSession
        from app.modules.parking.models import ParkingOccupancy, ParkingSpace

        # PRE-CLEANUP: تست‌های قبلی (مثل concurrent entry) نشست باز رها می‌کنند
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ParkingOccupancy))
            await db.execute(delete(ParkingSession))
            await db.commit()

        async with api_client() as ac:
            tok = await login(ac, "admin", "Admin@1234")
            h = auth(tok)

            r = await ac.post("/api/v1/parking/yard-spaces", headers=h,
                              json={"count": 3, "prefix": "YT"})
            j = r.json()
            assert r.status_code == 200 and j["created"] == ["YT-0001", "YT-0002", "YT-0003"], j
            r2 = await ac.post("/api/v1/parking/yard-spaces", headers=h,
                               json={"count": 3, "prefix": "YT"})
            assert r2.json()["created"] == [] and len(r2.json()["skipped_existing"]) == 3

            cs = (await ac.get("/api/v1/parking/capacity-status", headers=h)).json()
            assert cs["registered_yard_count"] >= 3 and "capacity_source" in cs, cs

            # ظرفیت از تنظیمات طراح (نه env) → موتور گیت زنده واکنش نشان می‌دهد
            await ac.put("/api/v1/app-settings/yard_capacity", headers=h,
                         json={"value": {"total": 1}, "reason": "yard-test"})
            try:
                b1 = {"gate_code": "GATE-IN-01", "direction": "IN",
                      "plate_raw": "12ب345ایران67", "source_event_id": "yd-1"}
                r1 = await ac.post("/api/v1/gate/events/plate-detected", json=b1, headers=GATE_HEADERS)
                assert r1.json()["decision"] == "ALLOW", r1.text
                b2 = {"gate_code": "GATE-IN-01", "direction": "IN",
                      "plate_raw": "34د567ایران89", "source_event_id": "yd-2"}
                r2b = await ac.post("/api/v1/gate/events/plate-detected", json=b2, headers=GATE_HEADERS)
                j2 = r2b.json()
                assert j2["decision"] == "REQUIRE_OPERATOR_APPROVAL", j2
                assert j2["decision_reason"] == "YARD_CAPACITY_FULL", j2
                cs2 = (await ac.get("/api/v1/parking/capacity-status", headers=h)).json()
                assert cs2["capacity_source"] == "setting" and cs2["declared_capacity"] == 1, cs2
                # خروج → ظرفیت آزاد
                await ac.post("/api/v1/gate/events/plate-detected",
                              json={**b1, "direction": "OUT", "source_event_id": "yd-3"},
                              headers=GATE_HEADERS)
                r3 = await ac.post("/api/v1/gate/events/plate-detected",
                                   json={**b2, "source_event_id": "yd-4"}, headers=GATE_HEADERS)
                assert r3.json()["decision"] == "ALLOW", r3.text
            finally:
                await ac.put("/api/v1/app-settings/yard_capacity", headers=h,
                             json={"value": {}, "reason": "cleanup"})

            # حذف جایگاه آزاد مجاز، 403 برای بدون مجوز
            spaces = (await ac.get("/api/v1/parking-spaces", headers=h)).json()
            yt = [s for s in spaces if s["code"] == "YT-0001"][0]
            d = await ac.delete(f"/api/v1/parking/yard-spaces/{yt['id']}", headers=h)
            assert d.status_code == 200, d.text
            tok2 = await login(ac, "op1", "Op@123456")
            d2 = await ac.post("/api/v1/parking/yard-spaces", headers=auth(tok2),
                               json={"count": 1, "prefix": "ZZ"})
            assert d2.status_code == 403

        async with AsyncSessionLocal() as db:
            await db.execute(delete(ParkingOccupancy))
            await db.execute(delete(ParkingSession))
            await db.execute(delete(ParkingSpace).where(ParkingSpace.code.like("YT-%")))
            await db.execute(text("DELETE FROM app_settings WHERE key='yard_capacity'"))
            await db.commit()
    run(go())
