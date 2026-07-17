from abc import ABC, abstractmethod
from typing import Any, Callable, Coroutine

class EventBus(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """Establish connections to the event broker."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connections cleanly."""
        pass

    @abstractmethod
    async def publish(self, stream_name: str, event_data: dict) -> str:
        """Publish an event payload to a specified event stream, returning the message ID."""
        pass

    @abstractmethod
    async def subscribe(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        handler: Callable[[str, dict], Coroutine[Any, Any, None]]
    ) -> None:
        """Subscribe to an event stream and execute the handler for incoming events."""
        pass
