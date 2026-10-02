"""wave2a: charges.paid_amount (partial payments F16) + tariffs approval columns (F8)

- charges.paid_amount BIGINT NOT NULL DEFAULT 0 + backfill از payment_allocations
- tariffs.approved_by / approved_at
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
    op.add_column("charges", sa.Column("paid_amount", sa.BigInteger(), nullable=False, server_default="0"))
    op.execute("""
        UPDATE charges
        SET paid_amount = (
            SELECT COALESCE(SUM(pa.amount), 0)
            FROM payment_allocations pa
            WHERE pa.charge_id = charges.id
        )
    """)
    op.execute("UPDATE charges SET status = 'PAID' WHERE paid_amount >= amount AND amount > 0")
    op.add_column("tariffs", sa.Column("approved_by", sa.String(length=36), nullable=True))
    op.add_column("tariffs", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("tariffs", "approved_at")
    op.drop_column("tariffs", "approved_by")
    op.drop_column("charges", "paid_amount")
