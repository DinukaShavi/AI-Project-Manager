"""add_organization_allowed_email_domains

Revision ID: 77a78bf17d67
Revises: 74c8df3bfc03
Create Date: 2026-08-09 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '77a78bf17d67'
down_revision: Union[str, None] = '74c8df3bfc03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Required by docs/api_contract.md "Get Organization Settings" response schema, which
    # was previously undeliverable — the field didn't exist on the model at all.
    op.add_column(
        'organizations',
        sa.Column('allowed_email_domains', postgresql.ARRAY(sa.String()), nullable=False, server_default='{}')
    )


def downgrade() -> None:
    op.drop_column('organizations', 'allowed_email_domains')
