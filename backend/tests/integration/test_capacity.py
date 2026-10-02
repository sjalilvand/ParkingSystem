"""Wave4a integration - capacity gate on real DB."""
from sqlalchemy import delete

from helpers import GATE_HEADERS, api_client, auth, login, run
from app.core.config import settings as app_settings


def test_capacity_gate_and_endpoints():
    async def go():
        from app.db.session import AsyncSessionLocal
        from app.modules.access_control.models import ParkingSession
        from app.modules.parking.models import ParkingOccupancy
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ParkingOccupancy))
            await db.execute(delete(ParkingSession))
            await db.commit()

        old = app_settings.YARD_CAPACITY_TOTAL
        app_settings.YARD_CAPACITY_TOTAL = 1
        try:
            async with api_client() as ac:
                tok = await login(ac, "admin", "Admin@1234")
                h = auth(tok)
                b1 = {"gate_code": "GATE-IN-01", "direction": "IN",
                      "plate_raw": "12ب345ایران67", "source_event_id": "cap-1"}
                r1 = await ac.post("/api/v1/gate/events/plate-detected", json=b1, headers=GATE_HEADERS)
                assert r1.status_code == 200 and r1.json()["decision"] == "ALLOW", r1.text

                b2 = {"gate_code": "GATE-IN-01", "direction": "IN",
                      "plate_raw": "34د567ایران89", "source_event_id": "cap-2"}
                r2 = await ac.post("/api/v1/gate/events/plate-detected", json=b2, headers=GATE_HEADERS)
                j2 = r2.json()
                assert j2["decision"] == "REQUIRE_OPERATOR_APPROVAL", j2
                assert j2["decision_reason"] == "YARD_CAPACITY_FULL", j2
                assert j2["barrier_action"] == "KEEP_CLOSED"

                st = (await ac.get("/api/v1/parking/capacity-status", headers=h)).json()
                assert st["declared_capacity"] == 1 and st["confirmed_presence"] == 1, st
                assert st["accepting"] is False and st["available"] == 0  # 1/1 = پر

                mm = await ac.post("/api/v1/parking/capacity-mismatch", headers=h,
                                   json={"observed": 3, "note": "extra cars in lane"})
                assert mm.status_code == 200 and mm.json()["success"] is True, mm.text

                r3 = await ac.post("/api/v1/gate/events/plate-detected",
                                   json={**b1, "direction": "OUT", "source_event_id": "cap-3"},
                                   headers=GATE_HEADERS)
                assert r3.status_code == 200 and r3.json()["decision"] == "ALLOW", r3.text

                r4 = await ac.post("/api/v1/gate/events/plate-detected",
                                   json={**b2, "source_event_id": "cap-4"}, headers=GATE_HEADERS)
                assert r4.status_code == 200 and r4.json()["decision"] == "ALLOW", r4.text

                # تخلیه کامل محوطه => پذیرش مجاز میشود (رفع ابهام تست قبلی)
                r5 = await ac.post("/api/v1/gate/events/plate-detected",
                                   json={**b2, "direction": "OUT", "source_event_id": "cap-5"},
                                   headers=GATE_HEADERS)
                assert r5.status_code == 200 and r5.json()["decision"] == "ALLOW", r5.text

                st2 = (await ac.get("/api/v1/parking/capacity-status", headers=h)).json()
                assert st2["confirmed_presence"] == 0 and st2["accepting"] is True, st2
                assert st2["available"] == 1, st2
        finally:
            app_settings.YARD_CAPACITY_TOTAL = old
            async with AsyncSessionLocal() as db:
                await db.execute(delete(ParkingOccupancy))
                await db.execute(delete(ParkingSession))
                await db.commit()
    run(go())
