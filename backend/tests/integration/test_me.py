"""Wave4b - /auth/me enriched (roles+permissions+is_admin)."""
from helpers import api_client, auth, login, run


def test_me_enriched_admin():
    async def go():
        async with api_client() as ac:
            tok = await login(ac, "admin", "Admin@1234")
            r = await ac.get("/auth/me", headers=auth(tok))
            assert r.status_code == 200, r.text
            j = r.json()
            assert j["is_admin"] is True, j
            assert "ADMIN" in j["roles"], j
            assert "finance.view" in j["permissions"], j
    run(go())
