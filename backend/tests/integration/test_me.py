"""Wave4b - /auth/me enriched (roles+permissions+is_admin)."""
from helpers import api_client, auth, login, run


def test_me_enriched_admin():
    async def go():
        async with api_client() as ac:
            tok = await login(ac, "admin", "Admin@1234")
            r = await ac.get("/api/v1/auth/me", headers=auth(tok))
            assert r.status_code == 200, r.text
            j = r.json()
            assert j["is_admin"] is True, j
            assert "ADMIN" in j["roles"], j
            assert "finance.view" in j["permissions"], j
            # کاربر محدود: بدون مجوز، بدون ادمین
            tok2 = await login(ac, "op1", "Op@123456")
            r2 = await ac.get("/api/v1/auth/me", headers=auth(tok2))
            j2 = r2.json()
            assert j2["is_admin"] is False, j2
            assert "LIMITED" in j2["roles"], j2
    run(go())
