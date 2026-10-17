"""p0005: اصلاح ایندکس نشست باز برای SQLite (partial index)

در دیتابیس‌های SQLite که با create_all ساخته شده‌اند، ایندکس uq_open_session_plate
به‌صورت کامل (روی همه ردیف‌ها) ساخته شده بود → ورود دوبارهٔ همان پلاک بعد از خروج
خطای IntegrityError می‌داد. این مهاجرت آن را به ایندکس partial (فقط status='OPEN')
تبدیل می‌کند. روی PostgreSQL کاری نمی‌کند (از قبل partial است).
Revision ID: p0005_sqlite_partial_uq
"""
from alembic import op
import sqlalchemy as sa

revision = "p0005_sqlite_partial_uq"
down_revision = "p0004_user_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return  # Postgres از p0001 ایندکس partial دارد
    op.drop_index("uq_open_session_plate", table_name="parking_sessions")
    op.create_index(
        "uq_open_session_plate",
        "parking_sessions",
        ["plate_normalized"],
        unique=True,
        sqlite_where=sa.text("status = 'OPEN'"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    op.drop_index("uq_open_session_plate", table_name="parking_sessions")
    op.create_index(
        "uq_open_session_plate", "parking_sessions", ["plate_normalized"], unique=True
    )
