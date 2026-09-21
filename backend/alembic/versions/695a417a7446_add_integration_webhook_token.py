"""add integration webhook_token

Revision ID: 695a417a7446
Revises: c7a2e4f1b9d6
Create Date: 2026-08-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "695a417a7446"
down_revision = "c7a2e4f1b9d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("integrations", sa.Column("webhook_token", sa.String(length=64), nullable=True))
    op.create_index("ix_integrations_webhook_token", "integrations", ["webhook_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_integrations_webhook_token", table_name="integrations")
    op.drop_column("integrations", "webhook_token")
