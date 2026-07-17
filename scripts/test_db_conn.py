import asyncio
import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def main():
    print(f"Connecting to database: {settings.async_database_url}")
    print(f"USE_PGVECTOR configuration is set to: {settings.USE_PGVECTOR}")
    
    # We will connect to default database 'postgres' first to verify/create 'aitpm' database.
    try:
        url_without_driver = settings.async_database_url.replace("postgresql+asyncpg://", "")
        auth, host_port_db = url_without_driver.split("@")
        username, password = auth.split(":")
        host_port, _ = host_port_db.split("/")
        host, port = host_port.split(":")
        
        print(f"Connecting to postgres system db on {host}:{port} with user {username}...")
        conn = await asyncpg.connect(
            user=username,
            password=password,
            host=host,
            port=int(port),
            database="postgres"
        )
        
        # Check if database 'aitpm' exists
        row = await conn.fetchrow("SELECT 1 FROM pg_database WHERE datname = 'aitpm';")
        if not row:
            print("Database 'aitpm' does not exist. Creating...")
            await conn.execute("CREATE DATABASE aitpm;")
            print("Successfully created database 'aitpm'!")
        else:
            print("Database 'aitpm' already exists.")
        await conn.close()
    except Exception as e:
        print(f"Database check/creation failed: {e}")

    # Now verify async connection to the 'aitpm' database using SQLAlchemy async engine
    engine = create_async_engine(settings.async_database_url)
    try:
        async with engine.connect() as conn:
            print("Successfully connected to 'aitpm' database via asyncpg!")
            from sqlalchemy import text
            # Enable pgvector only if configured
            if settings.USE_PGVECTOR:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                await conn.commit()
                print("pgvector extension enabled successfully.")
            else:
                print("pgvector extension bypassed (configured as USE_PGVECTOR=False).")
    except Exception as e:
        print(f"Async connection failed: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
