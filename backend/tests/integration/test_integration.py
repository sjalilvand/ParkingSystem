"""§21 scenarios - real DB, real app, concurrency interleaved on ONE persistent loop."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from helpers import GATE_HEADERS, api_client, auth, login, one_open_sessions, run


def test_gate_flow_and_idempotency():
    async def go():
        t0 = datetime.now(timezone.utc)
        async with api_client() as ac:
            body = {"gate_code": "GATE-IN-01", "direction": "IN", "plate_raw": "12ب345ایران67",
                    "source_event_id": "ev-1", "captured_at": t0.isoformat()}
            r1 = await ac.post("/api/v1/gate/events/plate-detected", json=body, headers=GATE_HEADERS)
            assert r1.status_code == 200, r1.text
            j1 = r1.json()
            assert j1["decision"] == "ALLOW" and j1["barrier_action"] == "OPEN"
            assert await one_open_sessions("12B345IR67") == 1

            r2 = await ac.post("/api/v1/gate/events/plate-detected", json=body, headers=GATE_HEADERS)
            j2 = r2.json()
            assert r2.status_code == 200 and j2["duplicate"] is True
            assert j2["access_event_id"] == j1["access_event_id"]

            body2 = {**body, "source_event_id": "ev-2"}
            r3 = await ac.post("/api/v1/gate/events/plate-detected", json=body2, headers=GATE_HEADERS)
            j3 = r3.json()
            assert r3.status_code == 200 and j3["decision"] == "ALLOW_WITH_WARNING"
            assert j3["decision_reason"] == "DUPLICATE_ENTRY_SESSION_OPEN"
            assert await one_open_sessions("12B345IR67") == 1

            r4 = await ac.post("/api/v1/gate/events/plate-detected",
                               json={**body, "direction": "OUT", "source_event_id": "ev-3",
                                     "captured_at": t0.isoformat()},
                               headers=GATE_HEADERS)
            j4 = r4.json()
            assert r4.status_code == 200 and j4["decision"] == "ALLOW", j4
            assert j4["session"]["payment_status"] == "FREE"
            assert await one_open_sessions("12B345IR67") == 0
    run(go())


def test_exit_unpaid_warn_and_charge():
    async def go():
        from app.modules.access_control.models import ParkingSession
        from app.modules.finance.models import Charge
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            db.add(ParkingSession(plate_normalized="34D567IR89",
                                  entry_at=datetime.now(timezone.utc) - timedelta(hours=2),
                                  status="OPEN"))
            await db.commit()
        async with api_client() as ac:
            r = await ac.post("/api/v1/gate/events/plate-detected",
                              json={"gate_code": "GATE-IN-01", "direction": "OUT",
                                    "plate_raw": "34د567ایران89", "source_event_id": "ev-out-1"},
                              headers=GATE_HEADERS)
            j = r.json()
            assert r.status_code == 200 and j["decision"] == "ALLOW", j
            assert "UNPAID_EXIT" in j["warnings"], j
            assert j["session"]["final_amount"] == 150_000
            async with AsyncSessionLocal() as db:
                ch = (await db.execute(select(Charge))).scalars().all()
                assert any(c.charge_type == "PARKING" and c.amount == 150_000 and c.status == "UNPAID" for c in ch)
    run(go())


def test_concurrent_entry_single_session_no_500():
    async def go():
        import asyncio
        async with api_client() as ac:
            bodies = [{"gate_code": "GATE-IN-01", "direction": "IN", "plate_raw": "12ب345ایران67",
                       "source_event_id": f"ev-c{i}"} for i in (1, 2)]
            rs = await asyncio.gather(*[
                ac.post("/api/v1/gate/events/plate-detected", json=b, headers=GATE_HEADERS) for b in bodies])
            for r in rs:
                assert r.status_code == 200, (r.status_code, r.text)
            decisions = {r.json()["decision"] for r in rs}
            assert "ALLOW" in decisions
            assert await one_open_sessions("12B345IR67") == 1
    run(go())


def test_payment_idempotency_partial_and_concurrent():
    async def go():
        import asyncio
        from app.modules.finance.models import Charge, Payment
        from app.modules.access_control.models import ParkingSession
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            ps = ParkingSession(plate_normalized="12B345IR67",
                                entry_at=datetime.now(timezone.utc) - timedelta(hours=1),
                                status="CLOSED")
            db.add(ps)
            await db.flush()
            db.add(Charge(parking_session_id=ps.id, charge_type="PARKING", amount=100_000, status="UNPAID"))
            await db.commit()
        async with api_client() as ac:
            tok = await login(ac, "admin", "Admin@1234")
            h = auth(tok)
            r1 = await ac.post("/api/v1/payments", headers=h, json={
                "plate_raw": "12ب345ایران67", "amount": 40_000, "reference_number": "REF-1"})
            j1 = r1.json()
            assert r1.status_code == 200 and j1["remaining_credit"] == 0 and not j1["duplicate"], j1
            d1 = (await ac.get("/api/v1/debts?plate=12ب345ایران67", headers=h)).json()
            assert d1["total_unpaid"] == 60_000 and d1["count"] == 1
            r2 = await ac.post("/api/v1/payments", headers=h, json={
                "plate_raw": "12ب345ایران67", "amount": 40_000, "reference_number": "REF-1"})
            assert r2.json()["duplicate"] is True
            d2 = (await ac.get("/api/v1/debts?plate=12ب345ایران67", headers=h)).json()
            assert d2["total_unpaid"] == 60_000
            r3 = await ac.post("/api/v1/payments", headers=h, json={
                "plate_raw": "12ب345ایران67", "amount": 60_000, "reference_number": "REF-2"})
            d3 = (await ac.get("/api/v1/debts?plate=12ب345ایران67", headers=h)).json()
            assert d3["count"] == 0 and d3["total_unpaid"] == 0
            rs = await asyncio.gather(*[
                ac.post("/api/v1/payments", headers=h, json={
                    "plate_raw": "12ب345ایران67", "amount": 10_000, "reference_number": "REF-C"})
                for _ in range(2)])
            for r in rs:
                assert r.status_code == 200, r.text
            flags = sorted([r.json()["duplicate"] for r in rs])
            assert flags == [False, True]
            async with AsyncSessionLocal() as db:
                pays = (await db.execute(select(Payment).where(Payment.reference_number == "REF-C"))).scalars().all()
                assert len(pays) == 1
    run(go())


def test_permissions_non_admin_403_admin_200():
    async def go():
        async with api_client() as ac:
            tok_limited = await login(ac, "op1", "Op@123456")
            tok_admin = await login(ac, "admin", "Admin@1234")
            r1 = await ac.get("/api/v1/tariffs", headers=auth(tok_limited))
            assert r1.status_code == 403, (r1.status_code, r1.text)
            r2 = await ac.post("/api/v1/gate/access/manual", headers=auth(tok_limited),
                               json={"gate_code": "GATE-IN-01", "plate_raw": "12ب345ایران67"})
            assert r2.status_code == 403, (r2.status_code, r2.text)
            r3 = await ac.get("/api/v1/violations", headers=auth(tok_limited))
            assert r3.status_code == 403, (r3.status_code, r3.text)
            r4 = await ac.get("/api/v1/tariffs", headers=auth(tok_admin))
            assert r4.status_code == 200
    run(go())


def test_violation_image_rule_and_voiding():
    async def go():
        async with api_client() as ac:
            tok = await login(ac, "admin", "Admin@1234")
            h = auth(tok)
            t = await ac.post("/api/v1/violations/types", headers=h, json={
                "code": "INT-IMG-1", "title": "تست", "default_penalty_amount": 20_000,
                "requires_image": True})
            assert t.status_code == 200, t.text
            r422 = await ac.post("/api/v1/violations", headers=h, json={
                "plate_raw": "12ب345ایران67", "violation_type_code": "INT-IMG-1"})
            assert r422.status_code == 422
            v = (await ac.post("/api/v1/violations", headers=h, json={
                "plate_raw": "12ب345ایران67", "violation_type_code": "INT-IMG-1",
                "image_file_id": "img-1"})).json()
            vid = v["id"]
            c = await ac.post(f"/api/v1/violations/{vid}/confirm", headers=h, json={})
            assert c.status_code == 200
            c2 = await ac.post(f"/api/v1/violations/{vid}/cancel", headers=h, json={"reason": "test"})
            assert c2.json()["charge_voided"] is True
            c3 = await ac.post(f"/api/v1/violations/{vid}/confirm", headers=h, json={})
            assert c3.status_code == 409
    run(go())
