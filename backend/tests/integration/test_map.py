"""Wave5h - bulk map coordinates."""
from helpers import api_client, auth, login, run


def test_map_coordinates_bulk_and_403():
    async def go():
        from app.modules.parking.models import ParkingSpace
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            sp = ParkingSpace(code="MAP-TEST-1", floor=0)
            db.add(sp)
            await db.commit()
            sid = sp.id
        async with api_client() as ac:
            tok = await login(ac, "admin", "Admin@1234")
            h = auth(tok)
            r = await ac.post("/api/v1/parking/map-coordinates", headers=h, json={
                "points": [{"space_id": sid, "x": 4231, "y": 5120}]})
            assert r.status_code == 200 and r.json()["updated"] == 1, r.text
            spaces = (await ac.get("/api/v1/parking-spaces", headers=h)).json()
            mine = [s for s in spaces if s["id"] == sid][0]
            assert mine["map_x"] == 4231 and mine["map_y"] == 5120, mine
            tok2 = await login(ac, "op1", "Op@123456")
            r2 = await ac.post("/api/v1/parking/map-coordinates", headers=auth(tok2), json={"points": []})
            assert r2.status_code == 403
    run(go())
