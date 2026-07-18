from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class BaseConnector(ABC):
    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify HMAC signature or secret header from incoming webhook."""
        pass

    @abstractmethod
    def parse_webhook_event(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        """Normalize raw webhook payload into standard event packet."""
        pass

    @abstractmethod
    async def fetch_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch remote data from platform REST API endpoints."""
        pass
