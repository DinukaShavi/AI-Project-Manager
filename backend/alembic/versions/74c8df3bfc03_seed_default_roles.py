"""seed_default_roles

Revision ID: 74c8df3bfc03
Revises: 9c8a7eecb85c
Create Date: 2026-08-08 23:05:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74c8df3bfc03'
down_revision: Union[str, None] = '9c8a7eecb85c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Must match app.core.rbac_pdp.UserRole exactly — that enum is what the Policy Decision
# Point actually enforces against a role NAME string, so these are the only role names
# that have any real effect on tool authorization today.
DEFAULT_ROLES = [
    ("SuperAdmin", "Full platform access, including destructive and prompt-modification actions."),
    ("OrgAdmin", "Organization-wide administrative access."),
    ("ProjectManager", "Project management and deployment approval access."),
    ("Developer", "Standard contributor access; default role granted on registration."),
    ("Viewer", "Read-only access."),
]


def upgrade() -> None:
    connection = op.get_bind()
    for name, description in DEFAULT_ROLES:
        existing = connection.execute(
            sa.text("SELECT id FROM roles WHERE name = :name"), {"name": name}
        ).fetchone()
        if existing:
            continue
        connection.execute(
            sa.text("INSERT INTO roles (id, name, description, created_at, updated_at) "
                    "VALUES (:id, :name, :description, now(), now())"),
            {"id": uuid.uuid4(), "name": name, "description": description}
        )


def downgrade() -> None:
    connection = op.get_bind()
    role_names = [name for name, _ in DEFAULT_ROLES]
    # Only remove roles that ended up with no users assigned, so we never silently
    # orphan a real assignment made after this migration ran.
    connection.execute(
        sa.text(
            "DELETE FROM roles WHERE name = ANY(:names) "
            "AND id NOT IN (SELECT role_id FROM user_roles)"
        ),
        {"names": role_names}
    )
