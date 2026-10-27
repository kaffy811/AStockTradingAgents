"""Persist stable Google subject identifiers."""
from alembic import op
import sqlalchemy as sa
revision = "s7t8u9v0w1x2"
down_revision = "r6s7t8u9v0w1"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("app_users", sa.Column("google_sub", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_app_users_google_sub", "app_users", ["google_sub"])

def downgrade():
    op.drop_constraint("uq_app_users_google_sub", "app_users", type_="unique")
    op.drop_column("app_users", "google_sub")
