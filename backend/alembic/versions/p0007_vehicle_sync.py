"""الحاقیه §۴ — جداول همگام‌سازی Google Sheets.

  vehicle_external_refs    نگاشت کلید مبدأ → خودرو (یکتا روی source_system+external_vehicle_id)
  vehicle_sync_runs        تاریخچهٔ اجراها (دستی/زمان‌بندی‌شده)
  vehicle_sync_conflicts   صف تعارض برای تعیین تکلیف انسانی
"""
from alembic import op
import sqlalchemy as sa

revision = "p0007_vehicle_sync"
down_revision = "p0006_plate_review"
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "vehicle_external_refs"):
        op.create_table(
            "vehicle_external_refs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("vehicle_id", sa.String(36),
                      sa.ForeignKey("vehicles.id"), nullable=False, index=True),
            sa.Column("source_system", sa.String(64), nullable=False, server_default="OPS"),
            sa.Column("external_vehicle_id", sa.String(128), nullable=False),
            sa.Column("external_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("source_system", "external_vehicle_id", name="uq_ext_ref_key"),
        )
    if not _table_exists(bind, "vehicle_sync_runs"):
        op.create_table(
            "vehicle_sync_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("trigger", sa.String(16), nullable=False, server_default="MANUAL"),
            sa.Column("status", sa.String(16), nullable=False, server_default="RUNNING"),
            sa.Column("spreadsheet_id", sa.String(128), nullable=True),
            sa.Column("worksheet", sa.String(128), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rows_total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rows_valid", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rows_created", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rows_updated", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rows_skipped", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("conflicts_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stats", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )
    if not _table_exists(bind, "vehicle_sync_conflicts"):
        op.create_table(
            "vehicle_sync_conflicts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("run_id", sa.String(36), nullable=True, index=True),
            sa.Column("row_number", sa.Integer(), nullable=True),
            sa.Column("external_vehicle_id", sa.String(128), nullable=True, index=True),
            sa.Column("source_system", sa.String(64), nullable=True, index=True),
            sa.Column("conflict_type", sa.String(32), nullable=False, index=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("incoming", sa.JSON(), nullable=True),
            sa.Column("current", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="PENDING", index=True),
            sa.Column("resolved_by", sa.String(36), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolution_note", sa.Text(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )


def downgrade() -> None:
    for t in ("vehicle_sync_conflicts", "vehicle_sync_runs", "vehicle_external_refs"):
        try:
            op.drop_table(t)
        except Exception:
            pass
