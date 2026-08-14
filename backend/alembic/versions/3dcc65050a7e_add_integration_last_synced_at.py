"""add_integration_last_synced_at

Revision ID: 3dcc65050a7e
Revises: 77a78bf17d67
Create Date: 2026-08-09 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3dcc65050a7e'
down_revision: Union[str, None] = '77a78bf17d67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backing field for the documented delta-sync backup poller (system_architecture_design.md's
    # Sync frequency matrix: "Celery Beat periodic pollers use delta-sync (modified_after /
    # last_synced_at)"). Nullable — a never-synced integration has no prior watermark yet.
    op.add_column('integrations', sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('integrations', 'last_synced_at')
