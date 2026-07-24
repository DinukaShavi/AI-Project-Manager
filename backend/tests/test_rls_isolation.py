import asyncio
import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
import app.db.base # Register models
from app.models.tenant import Organization, Workspace
from app.models.project import Project
from app.db.session import set_tenant_session_context, set_bypass_rls_context

# Async engine setup
engine = create_async_engine(settings.async_database_url)
SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False
)

async def test_rls_isolation_flow():
    print("Initializing PostgreSQL Row-Level Security (RLS) validation tests...")

    suffix = uuid.uuid4().hex[:6]
    domain_a = f"tenant-a-{suffix}.com"
    domain_b = f"tenant-b-{suffix}.com"

    async with SessionLocal() as session:
        # 1. Create a non-superuser role for testing RLS enforcement
        await session.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'test_rls_user') THEN
                    CREATE ROLE test_rls_user WITH LOGIN;
                END IF;
            END
            $$;
        """))
        await session.execute(text("GRANT USAGE ON SCHEMA public TO test_rls_user"))
        await session.execute(text("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO test_rls_user"))
        await session.execute(text("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO test_rls_user"))
        await session.commit()

    async with SessionLocal() as session:
        # Create test data under the superuser context (or bypass RLS context)
        await set_bypass_rls_context(session)

        tenant_a_id = uuid.uuid4()
        tenant_b_id = uuid.uuid4()

        org_a = Organization(id=tenant_a_id, name=f"Tenant A Corp {suffix}", domain=domain_a)
        org_b = Organization(id=tenant_b_id, name=f"Tenant B Corp {suffix}", domain=domain_b)

        session.add_all([org_a, org_b])
        await session.flush()

        workspace_a = Workspace(organization_id=tenant_a_id, name=f"Workspace A {suffix}")
        workspace_b = Workspace(organization_id=tenant_b_id, name=f"Workspace B {suffix}")

        session.add_all([workspace_a, workspace_b])
        await session.flush()

        project_a = Project(organization_id=tenant_a_id, workspace_id=workspace_a.id, name=f"Project A {suffix}")
        project_b = Project(organization_id=tenant_b_id, workspace_id=workspace_b.id, name=f"Project B {suffix}")

        session.add_all([project_a, project_b])
        await session.commit()

    # --- Test Case 1: Tenant A context restricts visibility strictly to Tenant A data under test_rls_user role ---
    async with SessionLocal() as session:
        # Switch to the test role
        await session.execute(text("SET ROLE test_rls_user"))
        
        # Set tenant session context
        await set_tenant_session_context(session, tenant_a_id)

        # 1. We should see Project A
        result = await session.execute(select(Project).where(Project.id == project_a.id))
        queried_proj_a = result.scalar_one_or_none()
        assert queried_proj_a is not None, "Tenant A should be able to see its own project"
        assert queried_proj_a.name == f"Project A {suffix}"

        # 2. We should NOT see Project B
        result = await session.execute(select(Project).where(Project.id == project_b.id))
        queried_proj_b = result.scalar_one_or_none()
        assert queried_proj_b is None, "Tenant A should NOT be able to see Tenant B's project (RLS leakage!)"

        # 3. We should see only Tenant A's projects when listing all
        result = await session.execute(select(Project))
        all_projects = result.scalars().all()
        # Filter list to just our test projects to avoid noise from existing seeded database items
        test_projects = [p for p in all_projects if p.id in (project_a.id, project_b.id)]
        assert len(test_projects) == 1, "Tenant A list query should only return 1 of the test projects"
        assert test_projects[0].id == project_a.id

        print("SUCCESS: Tenant A isolation and row invisibility verified.")

    # --- Test Case 2: Mismatched tenant inserts are blocked under test_rls_user role ---
    async with SessionLocal() as session:
        await session.execute(text("SET ROLE test_rls_user"))
        await set_tenant_session_context(session, tenant_a_id)

        from sqlalchemy.exc import DBAPIError
        try:
            mismatched_project = Project(
                organization_id=tenant_b_id,
                workspace_id=workspace_a.id,
                name=f"Mismatched Project {suffix}"
            )
            session.add(mismatched_project)
            await session.commit()
            raise AssertionError("Mismatched tenant insertion was NOT blocked by RLS check constraint!")
        except DBAPIError as e:
            await session.rollback()
            assert "violates row-level security policy" in str(e).lower(), f"Unexpected error: {e}"
            print("SUCCESS: Mismatched tenant insertion correctly blocked by RLS check policy.")

    # --- Test Case 3: Bypassing RLS permits full visibility under test_rls_user role ---
    async with SessionLocal() as session:
        await session.execute(text("SET ROLE test_rls_user"))
        await set_bypass_rls_context(session)

        # We should see both projects
        result = await session.execute(select(Project).where(Project.id.in_([project_a.id, project_b.id])))
        both_projects = result.scalars().all()
        assert len(both_projects) == 2, "Bypassing RLS should show projects from both tenants"

        print("SUCCESS: RLS bypass verified successfully.")

    # --- Cleanup ---
    async with SessionLocal() as session:
        # Reset role back to superuser
        await session.execute(text("RESET ROLE"))
        await set_bypass_rls_context(session)
        await session.execute(text("DELETE FROM projects WHERE id IN (:id_a, :id_b)"), {"id_a": project_a.id, "id_b": project_b.id})
        await session.execute(text("DELETE FROM workspaces WHERE id IN (:id_a, :id_b)"), {"id_a": workspace_a.id, "id_b": workspace_b.id})
        await session.execute(text("DELETE FROM organizations WHERE id IN (:id_a, :id_b)"), {"id_a": tenant_a_id, "id_b": tenant_b_id})
        await session.commit()
        print("Cleanup completed.")

    print("\nAll RLS isolation tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_rls_isolation_flow())
