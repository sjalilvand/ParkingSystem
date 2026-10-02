"""P0 audit wave1: dedupe OPEN parking sessions + partial unique index

- هر پلاک حداکثر یک نشست OPEN (سند بخش ۴: جلوگیری از چند جلسه فعال ناسازگار)
- نشست‌های باز تکراری موجود به CLOSED_ANOMALY علامت می‌خورند (هیچ داده‌ای حذف نمی‌شود)
Revision ID: p0001_open_session_uq
"""
from alembic import op
import sqlalchemy as sa

revision = "p0001_open_session_uq"
down_revision = "ae1f830b6c93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE parking_sessions
        SET status = 'CLOSED_ANOMALY',
            exit_at = COALESCE(exit_at, CURRENT_TIMESTAMP),
            updated_at = CURRENT_TIMESTAMP
        WHERE status = 'OPEN'
          AND id NOT IN (
              SELECT id FROM (
                  SELECT id,
                         ROW_NUMBER() OVER (PARTITION BY plate_normalized ORDER BY entry_at DESC) AS rn
                  FROM parking_sessions
                  WHERE status = 'OPEN'
              ) ranked
              WHERE ranked.rn = 1
          )
    """))
    op.create_index(
        "uq_open_session_plate",
        "parking_sessions",
        ["plate_normalized"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN'"),
        sqlite_where=sa.text("status = 'OPEN'"),
    )


def downgrade() -> None:
    op.drop_index("uq_open_session_plate", table_name="parking_sessions")

