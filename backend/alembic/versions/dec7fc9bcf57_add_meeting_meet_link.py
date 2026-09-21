"""add meeting meet_link

Revision ID: dec7fc9bcf57
Revises: 695a417a7446
Create Date: 2026-08-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "dec7fc9bcf57"
down_revision = "695a417a7446"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meetings", sa.Column("meet_link", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("meetings", "meet_link")
