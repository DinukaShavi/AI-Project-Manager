import asyncio
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import app.db.base # Register models
from app.core.config import settings
from app.events.redis_bus import get_event_bus
from app.models.tenant import Organization
from app.models.event import Event
from app.services.outbox import OutboxService
from app.db.session import SessionLocal

async def test_event_bus_and_outbox_flow():
    print("Initializing Event Bus and Outbox Service validation tests...")
    
    # Instantiate the dynamic Event Bus
    event_bus = get_event_bus()
    await event_bus.connect()
    print(f"Connected to Event Bus (Type: {type(event_bus).__name__}).")

    suffix = uuid.uuid4().hex[:6]
    test_org_id = None
    test_event_id = None
    event_received = asyncio.Event()
    received_payload = {}

    # Define subscriber callback handler
    async def sample_handler(msg_id: str, data: dict):
        print(f"Subscriber caught event: ID={msg_id}, data={data}")
        nonlocal received_payload
        received_payload = data
        event_received.set()

    # Subscribe handler to category stream
    # Category for 'project:created' is 'project' -> stream is 'project_stream'
    stream_name = "project_stream"
    await event_bus.subscribe(stream_name, "test_group", "test_consumer", sample_handler)
    print(f"Subscribed to stream: '{stream_name}'")

    try:
        # Create test outbox event record in the database
        async with SessionLocal() as session:
            print("\nInserting test outbox database entries...")
            org = Organization(name=f"Event Test Org {suffix}", domain=f"eventtest-{suffix}.com")
            session.add(org)
            await session.flush()
            test_org_id = org.id

            outbox_event = Event(
                organization_id=org.id,
                routing_key="project:created",
                payload={"project_name": "Nebula Core", "description": "AI coordination kernel"},
                processed=False
            )
            session.add(outbox_event)
            await session.commit()
            test_event_id = outbox_event.id
            print(f"Outbox record created. Event ID: {outbox_event.id}, processed={outbox_event.processed}")

        # Execute Outbox Service processor
        async with SessionLocal() as session:
            print("\nExecuting Outbox Service processor...")
            outbox_service = OutboxService(session)
            count = await outbox_service.process_outbox()
            assert count == 1, f"Expected 1 processed outbox record, got {count}"
            print("SUCCESS: Outbox record published successfully.")

        # Verify database record updated to processed=True
        async with SessionLocal() as session:
            res = await session.execute(select(Event).where(Event.id == test_event_id))
            queried_event = res.scalar_one()
            assert queried_event.processed is True
            print(f"SUCCESS: Database outbox record updated. processed={queried_event.processed}")

        # Wait for the Event Bus subscriber handler to execute
        print("\nWaiting for subscriber handler callback...")
        try:
            await asyncio.wait_for(event_received.wait(), timeout=5.0)
            print("SUCCESS: Subscriber triggered by Event Bus.")
            assert received_payload["routing_key"] == "project:created"
            assert received_payload["payload"]["project_name"] == "Nebula Core"
            print("SUCCESS: Received event payload matches original outbox data.")
        except asyncio.TimeoutError:
            raise AssertionError("Subscriber did not catch the published event within timeout.")

    finally:
        # Clean up database entries
        print("\nCleaning up test database entries...")
        async with SessionLocal() as session:
            if test_event_id:
                res = await session.execute(select(Event).where(Event.id == test_event_id))
                db_event = res.scalar_one_or_none()
                if db_event:
                    await session.delete(db_event)
            if test_org_id:
                res = await session.execute(select(Organization).where(Organization.id == test_org_id))
                db_org = res.scalar_one_or_none()
                if db_org:
                    await session.delete(db_org)
            await session.commit()
        await event_bus.disconnect()
        print("Cleanup completed.")

    print("\nAll Event Bus and Outbox integration tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_event_bus_and_outbox_flow())
