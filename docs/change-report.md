# گزارش تغییرات — ParkingSystem

| کامیت | موج | فایل‌ها | خلاصه |
|-------|-----|---------|-------|
| ef9a2b7 | ۱ | core/config, permissions, access_control/{service,router}, p0001, test_p0_audit | مجوز گیت، یکتایی نشست OPEN، سیاست خروج، fail-fast prod، پورت DB |
| cca1468 | ۱ | ae1f830b6c93 | تعمیر migration خراب legacy |
| 1c74fe4 | ۱ | p0001 | down_revision درست |
| d3d788f | ۱ | docs/* , .gitignore | سند مرجع + ممیزی v0.1 + تصمیمات معلق |
| 1d3638c | ۲a | finance/{models,service,router}, config, p0002, test_wave2_finance | جریان تصویب تعرفه، پرداخت جزئی، مجوز مالی، preview §۲۳ |
| (این کامیت) | ۲b | violations/{service,router}, parking/router, agent/decision, config, seed_audit_permissions, test_wave2_violations, docs | ابطال مستند بدهی تخلف، اعتبارسنجی تخصیص، max_entries آفلاین، کاتالوگ مجوز |

## دستور بازگشت (rollback)
- کد: `git revert <commit>` یا بازگشت به `audit/baseline-20261002-0805`
- DB: `docker exec -i parking-postgres psql -U parking -d parking_db < logs/db-backup-<stamp>.sql`
- Alembic: `alembic downgrade p0001_open_session_uq` (فقط p0002)
