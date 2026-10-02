"""Wave4g - چرخه کامل نقش (REQ-08-01) روی DB واقعی."""
from helpers import api_client, auth, login, run


def test_role_lifecycle_and_guards():
    async def go():
        async with api_client() as ac:
            tok = await login(ac, "admin", "Admin@1234")
            h = auth(tok)
            r = await ac.post("/api/v1/roles", headers=h, json={
                "code": "TESTING", "name": "تست نقش", "description": "d",
                "permission_codes": ["finance.view", "parking.manage"]})
            assert r.status_code == 200, r.text
            rid = r.json()["id"]

            roles = (await ac.get("/api/v1/roles", headers=h)).json()
            mine = [x for x in roles if x["code"] == "TESTING"]
            assert mine and sorted(mine[0]["permissions"]) == ["finance.view", "parking.manage"], mine

            r2 = await ac.post("/api/v1/roles", headers=h, json={"code": "TESTING", "name": "x"})
            assert r2.status_code == 409  # تکراری

            r3 = await ac.patch(f"/api/v1/roles/{rid}", headers=h,
                                json={"name": "تست ۲", "permission_codes": ["parking.view"]})
            assert r3.status_code == 200, r3.text
            roles2 = (await ac.get("/api/v1/roles", headers=h)).json()
            mine2 = [x for x in roles2 if x["code"] == "TESTING"][0]
            assert mine2["permissions"] == ["parking.view"] and mine2["title"] == "تست ۲", mine2

            cat = (await ac.get("/api/v1/roles/permissions-catalog", headers=h)).json()
            assert "finance" in cat and "parking" in cat, list(cat.keys())

            r4 = await ac.delete(f"/api/v1/roles/{rid}", headers=h)
            assert r4.status_code == 200, r4.text
            roles3 = (await ac.get("/api/v1/roles", headers=h)).json()
            assert not [x for x in roles3 if x["code"] == "TESTING"]

            admin_role = [x for x in roles3 if x["code"] == "ADMIN"][0]
            r5 = await ac.delete(f"/api/v1/roles/{admin_role['id']}", headers=h)
            assert r5.status_code == 409  # ادمین حذف نمیشود

            # کاربر بدون مجوز: 403
            tok2 = await login(ac, "op1", "Op@123456")
            r6 = await ac.get("/api/v1/roles", headers=auth(tok2))
            assert r6.status_code == 403, r6.status_code
    run(go())
