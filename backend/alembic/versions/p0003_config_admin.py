"""wave5a: config_admin foundation (همه غیرمخرب/افزودنی)
- vehicle_groups + vehicles.vehicle_group_id
- parking_sessions.usage_type (نوع استفاده در جلسه — REQ بخش۳)
- entry_exit_rules (قوانین ساختاریافته، بدون eval)
- app_settings + app_settings_history (نسخه‌بندی تنظیمات)
- receipt_templates, box_settings
- Idempotent: هر جدول/ستون/کلید فقط اگر نبود ساخته می‌شود تا روی پایگاه‌داده‌های
  create_all که این اشیا از قبل هستند، مهاجرت خطا ندهد (DuplicateTable و…)
Revision ID: p0003_config_admin
Revises: p0002_finance_paid_amount
"""
from alembic import op
import sqlalchemy as sa

revision = "p0003_config_admin"
down_revision = "p0002_finance_paid_amount"
branch_labels = None
depends_on = None

GROUPS = [
    ("11111111-1111-4111-8111-111111111101", "PRIMARY_COVERED", "خودروی اصلی دارای حق پارکینگ مسقف"),
    ("11111111-1111-4111-8111-111111111102", "SECONDARY_COVERED", "خودروی جایگزین دارای حق پارکینگ مسقف"),
    ("11111111-1111-4111-8111-111111111103", "RESIDENT_YARD", "خودروی ساکن متقاضی محوطه"),
    ("11111111-1111-4111-8111-111111111104", "NONRESIDENT_YARD", "خودروی غیرساکن متقاضی محوطه"),
    ("11111111-1111-4111-8111-111111111105", "SPECIAL_PERMIT", "خودروی دارای مجوز ویژه"),
]

def _kind(code: str) -> str:
    return ("PRIMARY_WITH_COVERED" if code == "PRIMARY_COVERED" else
            "SECONDARY_WITH_COVERED" if code == "SECONDARY_COVERED" else
            "RESIDENT_YARD" if code == "RESIDENT_YARD" else
            "SPECIAL_PERMIT" if code == "SPECIAL_PERMIT" else "NONRESIDENT_YARD")

def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    # ---------- vehicle_groups + رکوردهای پایه ----------
    if "vehicle_groups" not in tables:
        op.create_table(
            "vehicle_groups",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("code", sa.String(32), nullable=False, unique=True),
            sa.Column("title", sa.String(128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("membership_kind", sa.String(32), nullable=False, server_default="NONRESIDENT_YARD"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("default_tariff_id", sa.String(36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        print("  + vehicle_groups")
    for gid, code, title in GROUPS:
        exists = bind.execute(
            sa.text("SELECT 1 FROM vehicle_groups WHERE code=:c"), {"c": code}
        ).scalar()
        if exists is None:
            op.execute(sa.text(
                "INSERT INTO vehicle_groups (id, code, title, membership_kind, is_active, sort_order, created_at, updated_at) "
                "VALUES (:i,:c,:t,:k,true,:s,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            ).bindparams(i=gid, c=code, t=title, k=_kind(code), s=0))
            print(f"  + vehicle_group {code}")

    # ---------- vehicles.vehicle_group_id ----------
    if "vehicle_group_id" not in {c["name"] for c in sa.inspect(bind).get_columns("vehicles")}:
        op.add_column("vehicles", sa.Column("vehicle_group_id", sa.String(36), nullable=True))
        print("  + vehicles.vehicle_group_id")
    if bind.dialect.name == "postgresql":
        fk_names = {fk.get("name") for fk in sa.inspect(bind).get_foreign_keys("vehicles")}
        if "fk_vehicles_group" not in fk_names:
            op.create_foreign_key("fk_vehicles_group", "vehicles", "vehicle_groups",
                                  ["vehicle_group_id"], ["id"])
            print("  + fk_vehicles_group")

    # ---------- parking_sessions.usage_type ----------
    if "usage_type" not in {c["name"] for c in sa.inspect(bind).get_columns("parking_sessions")}:
        op.add_column("parking_sessions", sa.Column("usage_type", sa.String(24), nullable=True))
        print("  + parking_sessions.usage_type")

    # ---------- جدول‌های پیکربندی ----------
    if "entry_exit_rules" not in tables:
        op.create_table(
            "entry_exit_rules",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("direction", sa.String(8), nullable=False, server_default="ANY"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("condition_mode", sa.String(4), nullable=False, server_default="ALL"),
            sa.Column("conditions", sa.JSON(), nullable=False),
            sa.Column("actions", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(12), nullable=False, server_default="DRAFT"),
            sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(36), nullable=True),
            sa.Column("approved_by", sa.String(36), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        print("  + entry_exit_rules")
    if "app_settings" not in tables:
        op.create_table(
            "app_settings",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("key", sa.String(64), nullable=False, unique=True),
            sa.Column("value", sa.JSON(), nullable=False),
            sa.Column("updated_by", sa.String(36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        print("  + app_settings")
    if "app_settings_history" not in tables:
        op.create_table(
            "app_settings_history",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("key", sa.String(64), nullable=False, index=True),
            sa.Column("old_value", sa.JSON(), nullable=True),
            sa.Column("new_value", sa.JSON(), nullable=True),
            sa.Column("changed_by", sa.String(36), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        print("  + app_settings_history")
    if "receipt_templates" not in tables:
        op.create_table(
            "receipt_templates",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("paper_width_mm", sa.Integer(), nullable=False, server_default="80"),
            sa.Column("sections", sa.JSON(), nullable=False),
            sa.Column("header_text", sa.Text(), nullable=True),
            sa.Column("footer_text", sa.Text(), nullable=True),
            sa.Column("show_trial_badge", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        print("  + receipt_templates")
    if "box_settings" not in tables:
        op.create_table(
            "box_settings",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("side", sa.String(4), nullable=False, unique=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("buttons", sa.JSON(), nullable=False),
            sa.Column("messages", sa.JSON(), nullable=False),
            sa.Column("font_scale", sa.Float(), nullable=False, server_default="1.0"),
            sa.Column("colors", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        print("  + box_settings")

    from scripts.seed_config_defaults import seed_sync
    seed_sync(op.get_bind())

def downgrade() -> None:
    op.drop_table("box_settings")
    op.drop_table("receipt_templates")
    op.drop_table("app_settings_history")
    op.drop_table("app_settings")
    op.drop_table("entry_exit_rules")
    op.drop_column("parking_sessions", "usage_type")
    op.drop_constraint("fk_vehicles_group", "vehicles", type_="foreignkey")
    op.drop_column("vehicles", "vehicle_group_id")
    op.drop_table("vehicle_groups")
