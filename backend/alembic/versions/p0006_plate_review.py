"""الحاقیه §۳ — پاکت ثبت پلاک + مسیر تأیید انسانی.

ستون‌های جدید روی plate_recognition_events:
  plate_corrected / plate_corrected_normalized / corrected_by / corrected_at /
  correction_note / review_status / capture_quality / processing_ms

اصل حفظ سابقه: مقدار اصلی (plate_raw / plate_normalized) هرگز بازنویسی
نمی‌شود؛ اصلاح انسانی در ستون‌های corrected_* ثبت و تاریخچهٔ کامل (چه کسی/
کِی/چرا) حفظ می‌شود. review_status: AUTO_OK|NEEDS_REVIEW|CONFIRMED|CORRECTED|REJECTED
"""
from alembic import op
import sqlalchemy as sa

revision = "p0006_plate_review"
down_revision = "p0005_sqlite_partial_uq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = [
        sa.Column("plate_corrected", sa.String(64), nullable=True),
        sa.Column("plate_corrected_normalized", sa.String(32), nullable=True),
        sa.Column("corrected_by", sa.String(36), nullable=True),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correction_note", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(16), nullable=False, server_default="AUTO_OK"),
        sa.Column("capture_quality", sa.JSON(), nullable=True),
        sa.Column("processing_ms", sa.Integer(), nullable=True),
    ]
    table_names = ["plate_recognition_events"]
    bind = op.get_bind()
    for tname in table_names:
        insp = sa.inspect(bind)
        existing = {c["name"] for c in insp.get_columns(tname)}
        for col in cols:
            if col.name not in existing:
                op.add_column(tname, col)
        # ایندکس بازبینی (فقط اگر ستون تازه ساخته شده یا از قبل هست — idempotent)
        idx_names = {i["name"] for i in insp.get_indexes(tname)}
        if "ix_plate_recognition_review_status" not in idx_names:
            op.create_index("ix_plate_recognition_review_status", tname, ["review_status"])


def downgrade() -> None:
    op.drop_index("ix_plate_recognition_review_status", table_name="plate_recognition_events")
    for c in ("processing_ms", "capture_quality", "review_status", "correction_note",
              "corrected_at", "corrected_by", "plate_corrected_normalized", "plate_corrected"):
        try:
            op.drop_column("plate_recognition_events", c)
        except Exception:
            pass
