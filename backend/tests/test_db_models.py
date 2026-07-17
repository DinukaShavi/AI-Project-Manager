import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
import app.db.base # Register all models in SQLAlchemy
from app.models.tenant import Organization, Workspace, User
from app.models.project import Project
from app.models.memory import AgentMemory

# Async engine setup
engine = create_async_engine(settings.async_database_url)
SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False
)

async def test_db_operations():
    print("Starting database model integration tests...")
    
    import uuid
    suffix = uuid.uuid4().hex[:6]
    async with SessionLocal() as session:
        # 1. Test Organization, Workspace, and User Insertion
        print("\nTest 1: Inserting Tenant Models...")
        org = Organization(name=f"Acme Corp {suffix}", domain=f"acme-{suffix}.com")
        session.add(org)
        await session.flush() # populated UUID and timestamps
        print(f"Inserted Organization: ID={org.id}, name={org.name}, created_at={org.created_at}")

        workspace = Workspace(organization_id=org.id, name=f"Development Workspace {suffix}")
        session.add(workspace)
        await session.flush()
        print(f"Inserted Workspace: ID={workspace.id}, name={workspace.name}")

        user = User(organization_id=org.id, email=f"alice-{suffix}@acme.com", full_name="Alice Smith")
        session.add(user)
        await session.flush()
        print(f"Inserted User: ID={user.id}, email={user.email}")
        
        await session.commit()

        # Query and verify organization relationships
        from sqlalchemy.orm import selectinload
        result = await session.execute(
            select(Organization)
            .options(selectinload(Organization.workspaces), selectinload(Organization.users))
            .where(Organization.id == org.id)
        )
        queried_org = result.scalar_one()
        assert len(queried_org.workspaces) == 1
        assert len(queried_org.users) == 1
        print("SUCCESS: Tenant model relationships verified.")

        # 2. Test Soft Delete functionality
        print("\nTest 2: Testing Soft Delete...")
        assert user.deleted_at is None
        assert not user.is_deleted
        
        # Soft delete the user
        user.deleted_at = datetime.now(timezone.utc)
        await session.commit()
        
        # Refresh and verify
        await session.refresh(user)
        assert user.deleted_at is not None
        assert user.is_deleted
        print(f"SUCCESS: User soft-deleted (deleted_at={user.deleted_at}, is_deleted={user.is_deleted})")

        # 3. Test pgvector Embedding storage compatibility
        print("\nTest 3: Testing Embedding vector compatibility...")
        project = Project(workspace_id=workspace.id, name="AI Project")
        session.add(project)
        await session.flush()
        
        # Create a mock vector (size 1536)
        mock_embedding = [0.01] * 1536
        memory = AgentMemory(
            organization_id=org.id,
            project_id=project.id,
            memory_type="long_term",
            content="Summary context snapshot of the sprint status",
            embedding=mock_embedding
        )
        session.add(memory)
        await session.commit()

        # Retrieve and verify embedding
        res = await session.execute(select(AgentMemory).where(AgentMemory.id == memory.id))
        queried_memory = res.scalar_one()
        assert len(queried_memory.embedding) == 1536
        assert queried_memory.embedding[0] == 0.01
        print(f"SUCCESS: Vector embedding successfully stored and retrieved. Array size: {len(queried_memory.embedding)}")

        # Cleanup test data
        print("\nCleaning up test data...")
        await session.delete(queried_memory)
        await session.delete(project)
        await session.delete(user)
        await session.delete(workspace)
        await session.delete(queried_org)
        await session.commit()
        print("Cleanup completed successfully.")

    print("\nAll database model tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_db_operations())
