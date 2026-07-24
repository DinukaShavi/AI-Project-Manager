"""add_rls_policies

Revision ID: 9c8a7eecb85c
Revises: 3d4130946c29
Create Date: 2026-07-24 13:18:52.678167

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector
import pgvector.sqlalchemy


# revision identifiers, used by Alembic.
revision: str = '9c8a7eecb85c'
down_revision: Union[str, None] = '3d4130946c29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns as nullable first
    op.add_column('projects', sa.Column('organization_id', sa.UUID(), nullable=True))
    op.add_column('project_tasks', sa.Column('organization_id', sa.UUID(), nullable=True))
    op.add_column('repositories', sa.Column('organization_id', sa.UUID(), nullable=True))
    op.add_column('meetings', sa.Column('organization_id', sa.UUID(), nullable=True))
    op.add_column('tool_executions', sa.Column('organization_id', sa.UUID(), nullable=True))
    op.add_column('oauth_tokens', sa.Column('organization_id', sa.UUID(), nullable=True))
    op.add_column('context_snapshots', sa.Column('organization_id', sa.UUID(), nullable=True))
    op.add_column('knowledge_graph_edges', sa.Column('organization_id', sa.UUID(), nullable=True))
    op.add_column('workflow_executions', sa.Column('organization_id', sa.UUID(), nullable=True))
    op.add_column('analytics_metrics', sa.Column('organization_id', sa.UUID(), nullable=True))
    op.add_column('recommendations', sa.Column('organization_id', sa.UUID(), nullable=True))
    op.add_column('notifications', sa.Column('organization_id', sa.UUID(), nullable=True))
    op.add_column('context_embeddings', sa.Column('organization_id', sa.UUID(), nullable=True))

    # 2. Backfill organization_id from parent tables
    connection = op.get_bind()
    result = connection.execute(sa.text("SELECT id FROM organizations LIMIT 1")).fetchone()
    default_org_id = result[0] if result else None
    if not default_org_id:
        import uuid
        default_org_id = uuid.uuid4()
        connection.execute(
            sa.text("INSERT INTO organizations (id, name) VALUES (:id, 'Default Organization')"),
            {"id": default_org_id}
        )

    # Perform updates using SQL Joins
    connection.execute(sa.text("UPDATE projects SET organization_id = workspaces.organization_id FROM workspaces WHERE projects.workspace_id = workspaces.id"))
    connection.execute(sa.text("UPDATE project_tasks SET organization_id = projects.organization_id FROM projects WHERE project_tasks.project_id = projects.id"))
    connection.execute(sa.text("UPDATE repositories SET organization_id = projects.organization_id FROM projects WHERE repositories.project_id = projects.id"))
    connection.execute(sa.text("UPDATE meetings SET organization_id = projects.organization_id FROM projects WHERE meetings.project_id = projects.id"))
    connection.execute(sa.text("UPDATE tool_executions SET organization_id = agent_executions.organization_id FROM agent_executions WHERE tool_executions.agent_execution_id = agent_executions.id"))
    connection.execute(sa.text("UPDATE oauth_tokens SET organization_id = integrations.organization_id FROM integrations WHERE oauth_tokens.integration_id = integrations.id"))
    connection.execute(sa.text("UPDATE context_snapshots SET organization_id = projects.organization_id FROM projects WHERE context_snapshots.project_id = projects.id"))
    connection.execute(sa.text("UPDATE knowledge_graph_edges SET organization_id = projects.organization_id FROM projects WHERE knowledge_graph_edges.project_id = projects.id"))
    connection.execute(sa.text("UPDATE workflow_executions SET organization_id = workflows.organization_id FROM workflows WHERE COALESCE(workflow_executions.workflow_definition_id, workflow_executions.workflow_id) = workflows.id"))
    connection.execute(sa.text("UPDATE analytics_metrics SET organization_id = projects.organization_id FROM projects WHERE analytics_metrics.project_id = projects.id"))
    connection.execute(sa.text("UPDATE recommendations SET organization_id = projects.organization_id FROM projects WHERE recommendations.project_id = projects.id"))
    connection.execute(sa.text("UPDATE notifications SET organization_id = users.organization_id FROM users WHERE notifications.user_id = users.id"))
    connection.execute(sa.text("UPDATE context_embeddings SET organization_id = context_chunks.organization_id FROM context_chunks WHERE context_embeddings.chunk_id = context_chunks.id"))

    # Backfill default org ID for any remaining NULL values
    tables = [
        'projects', 'project_tasks', 'repositories', 'meetings',
        'tool_executions', 'oauth_tokens', 'context_snapshots',
        'knowledge_graph_edges', 'workflow_executions', 'analytics_metrics',
        'recommendations', 'notifications', 'context_embeddings'
    ]
    for table in tables:
        connection.execute(
            sa.text(f"UPDATE {table} SET organization_id = :org_id WHERE organization_id IS NULL"),
            {"org_id": default_org_id}
        )

    # 3. Alter columns to NOT NULL, create foreign keys and indexes
    for table in tables:
        op.alter_column(table, 'organization_id', nullable=False)
        op.create_foreign_key(f"fk_{table}_organization_id", table, "organizations", ["organization_id"], ["id"], ondelete="CASCADE")
        op.create_index(f"idx_{table}_organization_id", table, ["organization_id"])

    # 4. Enable RLS and create isolation policies on all tenant tables
    all_tenant_tables = [
        'workspaces', 'users', 'integrations', 'events', 'workflows',
        'workflow_executions', 'agent_executions', 'agent_plans',
        'model_configurations', 'audit_logs', 'agent_memories', 'context_chunks',
        'projects', 'project_tasks', 'repositories', 'meetings',
        'tool_executions', 'oauth_tokens', 'context_snapshots',
        'knowledge_graph_edges', 'analytics_metrics',
        'recommendations', 'notifications', 'context_embeddings'
    ]
    for table in all_tenant_tables:
        connection.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;"))
        connection.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;"))
        connection.execute(sa.text(f"""
            CREATE POLICY tenant_isolation_policy ON {table}
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

    # 1. Drop RLS Policies and Disable RLS
    all_tenant_tables = [
        'workspaces', 'users', 'integrations', 'events', 'workflows',
        'workflow_executions', 'agent_executions', 'agent_plans',
        'model_configurations', 'audit_logs', 'agent_memories', 'context_chunks',
        'projects', 'project_tasks', 'repositories', 'meetings',
        'tool_executions', 'oauth_tokens', 'context_snapshots',
        'knowledge_graph_edges', 'analytics_metrics',
        'recommendations', 'notifications', 'context_embeddings'
    ]
    for table in all_tenant_tables:
        connection.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};"))
        connection.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"))

    # 2. Drop Foreign Keys, Indexes and Columns
    tables = [
        'projects', 'project_tasks', 'repositories', 'meetings',
        'tool_executions', 'oauth_tokens', 'context_snapshots',
        'knowledge_graph_edges', 'workflow_executions', 'analytics_metrics',
        'recommendations', 'notifications', 'context_embeddings'
    ]
    for table in tables:
        op.drop_constraint(f"fk_{table}_organization_id", table, type_='foreignkey')
        op.drop_index(f"idx_{table}_organization_id", table_name=table)
        op.drop_column(table, 'organization_id')

