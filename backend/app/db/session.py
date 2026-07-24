from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# 1. Async Engine & Sessionmaker (Primary for app runs)
async_engine = create_async_engine(
    settings.async_database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)
SessionLocal = async_sessionmaker(
    bind=async_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

# 2. Sync Engine & Sessionmaker (Fallback / Alembic env helper)
# Commented out to avoid psycopg2 dependency since the application uses async connections exclusively.
# sync_url = settings.async_database_url.replace("postgresql+asyncpg://", "postgresql://")
# sync_engine = create_engine(sync_url, pool_pre_ping=True)
# SyncSessionLocal = sessionmaker(
#     bind=sync_engine,
#     autocommit=False,
#     autoflush=False
# )

from sqlalchemy import text, event
from uuid import UUID
from typing import Optional
import contextvars
from sqlalchemy.orm import Session

# Context variables for request-scoped tenant storage
current_tenant: contextvars.ContextVar[Optional[UUID]] = contextvars.ContextVar("current_tenant", default=None)
bypass_rls: contextvars.ContextVar[bool] = contextvars.ContextVar("bypass_rls", default=False)

async def set_tenant_session_context(session: AsyncSession, tenant_id: UUID | str) -> None:
    """Set app.current_tenant_id session config variable for RLS."""
    t_id = UUID(str(tenant_id)) if isinstance(tenant_id, str) else tenant_id
    current_tenant.set(t_id)
    await session.execute(
        text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)}
    )

async def set_bypass_rls_context(session: AsyncSession) -> None:
    """Set app.bypass_rls session config variable to bypass RLS in current transaction."""
    bypass_rls.set(True)
    await session.execute(
        text("SELECT set_config('app.bypass_rls', 'true', true)")
    )

@event.listens_for(Session, "before_flush")
def before_flush_listener(session, flush_context, instances):
    t_id = current_tenant.get()
    
    for obj in session.new:
        if not hasattr(obj, "organization_id"):
            continue
        if getattr(obj, "organization_id", None) is not None:
            continue
            
        # 1. Try Request Context Variable
        if t_id:
            setattr(obj, "organization_id", t_id)
            continue
            
        # 2. Try traversing relationships to resolve parent's organization_id
        ref_table = obj.__tablename__
        parent_org_id = None
        
        if ref_table == "projects":
            if getattr(obj, "workspace", None) is not None:
                parent_org_id = obj.workspace.organization_id
            elif getattr(obj, "workspace_id", None):
                from app.models.tenant import Workspace
                ws = session.get(Workspace, obj.workspace_id)
                if ws:
                    parent_org_id = ws.organization_id
        elif ref_table == "project_tasks":
            if getattr(obj, "project", None) is not None:
                parent_org_id = obj.project.organization_id
            elif getattr(obj, "project_id", None):
                from app.models.project import Project
                p = session.get(Project, obj.project_id)
                if p:
                    parent_org_id = p.organization_id
        elif ref_table == "repositories":
            if getattr(obj, "project", None) is not None:
                parent_org_id = obj.project.organization_id
            elif getattr(obj, "project_id", None):
                from app.models.project import Project
                p = session.get(Project, obj.project_id)
                if p:
                    parent_org_id = p.organization_id
        elif ref_table == "meetings":
            if getattr(obj, "project", None) is not None:
                parent_org_id = obj.project.organization_id
            elif getattr(obj, "project_id", None):
                from app.models.project import Project
                p = session.get(Project, obj.project_id)
                if p:
                    parent_org_id = p.organization_id
        elif ref_table == "tool_executions":
            if getattr(obj, "agent_execution", None) is not None:
                parent_org_id = obj.agent_execution.organization_id
            elif getattr(obj, "agent_execution_id", None):
                from app.models.agent import AgentExecution
                ae = session.get(AgentExecution, obj.agent_execution_id)
                if ae:
                    parent_org_id = ae.organization_id
        elif ref_table == "oauth_tokens":
            if getattr(obj, "integration", None) is not None:
                parent_org_id = obj.integration.organization_id
            elif getattr(obj, "integration_id", None):
                from app.models.integration import Integration
                i = session.get(Integration, obj.integration_id)
                if i:
                    parent_org_id = i.organization_id
        elif ref_table == "context_snapshots":
            if getattr(obj, "project", None) is not None:
                parent_org_id = obj.project.organization_id
            elif getattr(obj, "project_id", None):
                from app.models.project import Project
                p = session.get(Project, obj.project_id)
                if p:
                    parent_org_id = p.organization_id
        elif ref_table == "knowledge_graph_edges":
            if getattr(obj, "project", None) is not None:
                parent_org_id = obj.project.organization_id
            elif getattr(obj, "project_id", None):
                from app.models.project import Project
                p = session.get(Project, obj.project_id)
                if p:
                    parent_org_id = p.organization_id
        elif ref_table == "workflow_executions":
            if getattr(obj, "workflow", None) is not None:
                parent_org_id = obj.workflow.organization_id
            else:
                from app.models.workflow import WorkflowDefinition
                wf_id = getattr(obj, "workflow_definition_id", None) or getattr(obj, "workflow_id", None)
                if wf_id:
                    wd = session.get(WorkflowDefinition, wf_id)
                    if wd:
                        parent_org_id = wd.organization_id
        elif ref_table == "analytics_metrics":
            if getattr(obj, "project", None) is not None:
                parent_org_id = obj.project.organization_id
            elif getattr(obj, "project_id", None):
                from app.models.project import Project
                p = session.get(Project, obj.project_id)
                if p:
                    parent_org_id = p.organization_id
        elif ref_table == "recommendations":
            if getattr(obj, "project", None) is not None:
                parent_org_id = obj.project.organization_id
            elif getattr(obj, "project_id", None):
                from app.models.project import Project
                p = session.get(Project, obj.project_id)
                if p:
                    parent_org_id = p.organization_id
        elif ref_table == "notifications":
            if getattr(obj, "user", None) is not None:
                parent_org_id = obj.user.organization_id
            elif getattr(obj, "user_id", None):
                from app.models.tenant import User
                u = session.get(User, obj.user_id)
                if u:
                    parent_org_id = u.organization_id
        elif ref_table == "context_embeddings":
            if getattr(obj, "chunk", None) is not None:
                parent_org_id = obj.chunk.organization_id
            elif getattr(obj, "chunk_id", None):
                from app.models.context import ContextChunk
                cc = session.get(ContextChunk, obj.chunk_id)
                if cc:
                    parent_org_id = cc.organization_id
                    
        if parent_org_id:
            setattr(obj, "organization_id", parent_org_id)
            continue

        # 3. Fallback: Check other objects in session.new
        for other_obj in session.new:
            if hasattr(other_obj, "organization_id") and getattr(other_obj, "organization_id", None) is not None:
                parent_org_id = other_obj.organization_id
                break

        if parent_org_id:
            setattr(obj, "organization_id", parent_org_id)
            continue

        # 4. Fallback: Query first organization in database
        from app.models.tenant import Organization
        first_org = session.query(Organization).first()
        if first_org:
            setattr(obj, "organization_id", first_org.id)



