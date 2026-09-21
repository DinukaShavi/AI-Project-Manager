"""add tool_approvals table (Phase 86: real human-in-the-loop approval grants)

Revision ID: e4b9c2a71f38
Revises: dec7fc9bcf57
Create Date: 2026-09-15

Backs implementation_roadmap.md Milestone 12 ("mutating tools wait for approval"). Before
this, ToolExecutor accepted any non-empty approval_token string, so the gate was bypassable.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e4b9c2a71f38'
down_revision: Union[str, None] = 'dec7fc9bcf57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tool_approvals',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('requested_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('approved_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('tool_parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('parameters_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('approval_token_hash', sa.String(length=64), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tool_approvals_organization_id', 'tool_approvals', ['organization_id'])
    op.create_index('ix_tool_approvals_tool_name', 'tool_approvals', ['tool_name'])
    op.create_index('ix_tool_approvals_status', 'tool_approvals', ['status'])
    # Token lookup during validation goes through this index; the raw token is never stored.
    op.create_index('ix_tool_approvals_approval_token_hash', 'tool_approvals', ['approval_token_hash'])


def downgrade() -> None:
    op.drop_index('ix_tool_approvals_approval_token_hash', table_name='tool_approvals')
    op.drop_index('ix_tool_approvals_status', table_name='tool_approvals')
    op.drop_index('ix_tool_approvals_tool_name', table_name='tool_approvals')
    op.drop_index('ix_tool_approvals_organization_id', table_name='tool_approvals')
    op.drop_table('tool_approvals')
