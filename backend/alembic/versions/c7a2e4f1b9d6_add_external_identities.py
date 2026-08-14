"""add external identities and integration workspace metadata

Revision ID: c7a2e4f1b9d6
Revises: b3f7a1c9e2d4
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7a2e4f1b9d6'
down_revision: Union[str, None] = 'b3f7a1c9e2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('integrations', sa.Column('external_workspace_id', sa.String(length=255), nullable=True))
    op.add_column('integrations', sa.Column('external_workspace_name', sa.String(length=255), nullable=True))

    op.create_table('external_identities',
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('integration_id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('external_account_id', sa.String(length=255), nullable=False),
        sa.Column('external_display_name', sa.String(length=255), nullable=True),
        sa.Column('verified_via_oauth', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_external_identities_id'), 'external_identities', ['id'], unique=False)
    op.create_index(op.f('ix_external_identities_organization_id'), 'external_identities', ['organization_id'], unique=False)
    op.create_index(op.f('ix_external_identities_user_id'), 'external_identities', ['user_id'], unique=False)
    op.create_index(op.f('ix_external_identities_integration_id'), 'external_identities', ['integration_id'], unique=False)

    # Partial unique indexes: uniqueness enforced only among ACTIVE rows, so unlinking
    # (is_active=False) and later re-linking the same external account never collides with
    # its own inactive history.
    op.create_index(
        'uq_external_identity_active_account', 'external_identities',
        ['organization_id', 'provider', 'external_account_id'],
        unique=True, postgresql_where=sa.text('is_active = true'),
    )
    op.create_index(
        'uq_external_identity_active_user_provider', 'external_identities',
        ['organization_id', 'user_id', 'provider'],
        unique=True, postgresql_where=sa.text('is_active = true'),
    )


def downgrade() -> None:
    op.drop_index('uq_external_identity_active_user_provider', table_name='external_identities')
    op.drop_index('uq_external_identity_active_account', table_name='external_identities')
    op.drop_index(op.f('ix_external_identities_integration_id'), table_name='external_identities')
    op.drop_index(op.f('ix_external_identities_user_id'), table_name='external_identities')
    op.drop_index(op.f('ix_external_identities_organization_id'), table_name='external_identities')
    op.drop_index(op.f('ix_external_identities_id'), table_name='external_identities')
    op.drop_table('external_identities')
    op.drop_column('integrations', 'external_workspace_name')
    op.drop_column('integrations', 'external_workspace_id')
