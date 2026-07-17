from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
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
