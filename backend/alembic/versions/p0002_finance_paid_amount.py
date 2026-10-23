"""wave2a: charges.paid_amount (partial payments F16) + tariffs approval columns (F8)

- charges.paid_amount BIGINT NOT NULL DEFAULT 0 + backfill از payment_allocations
- tariffs.approved_by / approved_at
- Idempotent: هر ستون فقط اگر نبود اضافه می‌شود؛ backfill هم فقط وقتی اجرا
  می‌شود که ستون تازه ساخته شده باشد (در پایگاه‌دادهٔ create_all ستون از قبل
  هست و مقادیرش توسط خود برنامه نگهداری شده — نباید بازنویسی شود)
Revision ID: p0002_finance_paid_amount
Revises: p0001_open_session_uq
"""
from alembic import op
import sqlalchemy as sa

revision = "p0002_finance_paid_amount"
down_revision = "p0001_open_session_uq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    def cols(table: str) -> set[str]:
        return {c["name"] for c in sa.inspect(bind).get_columns(table)}

    if "paid_amount" not in cols("charges"):
        op.add_column("charges", sa.Column("paid_amount", sa.BigInteger(), nullable=False, server_default="0"))
        print("  + charges.paid_amount")
        # backfill فقط برای ستون تازه‌ساخته‌شده
        bind.execute(sa.text("""
            UPDATE charges
            SET paid_amount = (
                SELECT COALESCE(SUM(pa.amount), 0)
                FROM payment_allocations pa
                WHERE pa.charge_id = charges.id
            )
        """))
        bind.execute(sa.text("UPDATE charges SET status = 'PAID' WHERE paid_amount >= amount AND amount > 0"))
    else:
        print("  = charges.paid_amount already exists → skip")

    if "approved_by" not in cols("tariffs"):
        op.add_column("tariffs", sa.Column("approved_by", sa.String(length=36), nullable=True))
        print("  + tariffs.approved_by")
    if "approved_at" not in cols("tariffs"):
        op.add_column("tariffs", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        print("  + tariffs.approved_at")


def downgrade() -> None:
    op.drop_column("tariffs", "approved_at")
    op.drop_column("tariffs", "approved_by")
    op.drop_column("charges", "paid_amount")
