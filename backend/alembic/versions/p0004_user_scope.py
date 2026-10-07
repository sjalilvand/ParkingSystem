"""wave5k: users scope columns (F26 - model fields since cb898df had no migration)
Revision ID: p0004_user_scope
Revises: p0003_config_admin
"""
from alembic import op
import sqlalchemy as sa

revision = "p0004_user_scope"
down_revision = "p0003_config_admin"
branch_labels = None
depends_on = None

COLUMNS = [
    ("scope_type",       sa.String(16),  "'ALL'"),
    ("scope_tower_ids",  sa.Text(),      "None"),
    ("scope_yard_ids",   sa.Text(),      "None"),
    ("scope_plan_ids",   sa.Text(),      "None"),
]

def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("users")}
    for name, coltype, default in COLUMNS:
        if name not in cols:
            kwargs = {"nullable": True}
            if default != "None":
                kwargs["server_default"] = sa.text(default)
            op.add_column("users", sa.Column(name, coltype, **kwargs))
            print(f"  + users.{name}")

def downgrade() -> None:
    for name, _t, _d in reversed(COLUMNS):
        op.drop_column("users", name)
