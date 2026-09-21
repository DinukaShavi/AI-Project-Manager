"""add events.dead_lettered_at (Phase 87: Milestone 4 Dead Letter Queue)

Revision ID: f1a3d8c26b95
Revises: e4b9c2a71f38
Create Date: 2026-09-15

implementation_roadmap.md Milestone 4 DoD: "failed tasks route to DLQ". Before this there was
no DLQ concept at all -- a permanently-failing outbox event was retried every second forever.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a3d8c26b95'
down_revision: Union[str, None] = 'e4b9c2a71f38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('events', sa.Column('dead_lettered_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_events_dead_lettered_at', 'events', ['dead_lettered_at'])


def downgrade() -> None:
    op.drop_index('ix_events_dead_lettered_at', table_name='events')
    op.drop_column('events', 'dead_lettered_at')
