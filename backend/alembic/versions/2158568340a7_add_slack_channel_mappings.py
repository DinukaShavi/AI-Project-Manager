"""add_slack_channel_mappings

Revision ID: 2158568340a7
Revises: 3dcc65050a7e
Create Date: 2026-08-09 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2158568340a7'
down_revision: Union[str, None] = '3dcc65050a7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Slack channel-to-project mappings (implementation_roadmap.md Milestone 9's documented
    # "Database Changes"; api_contract.md section 6.A "Map Project to Slack Channel"). A channel
    # maps to at most one project, so incoming webhook messages can be routed unambiguously.
    op.create_table(
        'slack_channel_mappings',
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('slack_channel_id', sa.String(length=50), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slack_channel_id', name='uq_slack_channel_mappings_slack_channel_id'),
    )
    op.create_index(op.f('ix_slack_channel_mappings_id'), 'slack_channel_mappings', ['id'], unique=False)
    op.create_index('idx_slack_channel_mappings_organization_id', 'slack_channel_mappings', ['organization_id'])

    # Enable RLS from creation, matching the tenant_isolation_policy established for every other
    # tenant table in 9c8a7eecb85c_add_rls_policies.py.
    connection = op.get_bind()
    connection.execute(sa.text("ALTER TABLE slack_channel_mappings ENABLE ROW LEVEL SECURITY;"))
    connection.execute(sa.text("ALTER TABLE slack_channel_mappings FORCE ROW LEVEL SECURITY;"))
    connection.execute(sa.text("""
        CREATE POLICY tenant_isolation_policy ON slack_channel_mappings
        FOR ALL
        USING (
            (current_setting('app.bypass_rls', true) = 'true')
            OR
            (organization_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
        )
        WITH CHECK (
            (current_setting('app.bypass_rls', true) = 'true')
            OR
            (organization_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
        );
    """))


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation_policy ON slack_channel_mappings;"))
    connection.execute(sa.text("ALTER TABLE slack_channel_mappings DISABLE ROW LEVEL SECURITY;"))
    op.drop_index('idx_slack_channel_mappings_organization_id', table_name='slack_channel_mappings')
    op.drop_index(op.f('ix_slack_channel_mappings_id'), table_name='slack_channel_mappings')
    op.drop_table('slack_channel_mappings')
