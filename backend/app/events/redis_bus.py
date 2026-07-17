import asyncio
import uuid
from typing import Any, Callable, Coroutine, Dict, List
import redis.asyncio as aioredis
from app.core.config import settings
from app.events.base import EventBus

class RedisEventBus(EventBus):
    def __init__(self, url: str):
        """Production Redis Streams Event Bus implementation."""
        self.url = url
        self.client = None

    async def connect(self) -> None:
        self.client = aioredis.from_url(self.url, decode_responses=True)

    async def disconnect(self) -> None:
        if self.client:
            await self.client.aclose()

    async def publish(self, stream_name: str, event_data: dict) -> str:
        # Convert nested complex dictionaries/lists into flat string format for Redis compatibility
        flat_data = {k: str(v) if isinstance(v, (dict, list)) else v for k, v in event_data.items()}
        msg_id = await self.client.xadd(stream_name, flat_data)
        return msg_id

    async def subscribe(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        handler: Callable[[str, dict], Coroutine[Any, Any, None]]
    ) -> None:
        # Ensure the consumer group exists
        try:
            await self.client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        except Exception:
            pass  # Consumer group already exists

        while True:
            try:
                # Read new messages from the stream
                streams = await self.client.xreadgroup(
                    groupname=group_name,
                    consumername=consumer_name,
                    streams={stream_name: ">"},
                    count=1,
                    block=2000
                )
                if streams:
                    for stream, messages in streams:
                        for msg_id, payload in messages:
                            await handler(msg_id, payload)
                            # Acknowledge the message upon successful execution
                            await self.client.xack(stream_name, group_name, msg_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log broker errors and sleep briefly before retry to prevent spinlocks
                await asyncio.sleep(1)


class InMemoryEventBus(EventBus):
    def __init__(self):
        """Local-only In-Memory Event Bus mock fallback for developer environments without Redis."""
        self.subscribers: Dict[str, List[Callable[[str, dict], Coroutine[Any, Any, None]]]] = {}

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def publish(self, stream_name: str, event_data: dict) -> str:
        msg_id = str(uuid.uuid4())
        handlers = self.subscribers.get(stream_name, [])
        for handler in handlers:
            # Dispatch event execution asynchronously on the background loop
            asyncio.create_task(handler(msg_id, event_data))
        return msg_id

    async def subscribe(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        handler: Callable[[str, dict], Coroutine[Any, Any, None]]
    ) -> None:
        if stream_name not in self.subscribers:
            self.subscribers[stream_name] = []
        self.subscribers[stream_name].append(handler)


# Singleton instance manager
_event_bus_instance: EventBus = None

def get_event_bus() -> EventBus:
    """Get the active Event Bus singleton based on configuration."""
    global _event_bus_instance
    if _event_bus_instance is None:
        if settings.USE_REDIS:
            _event_bus_instance = RedisEventBus(settings.redis_url_str)
        else:
            _event_bus_instance = InMemoryEventBus()
    return _event_bus_instance
