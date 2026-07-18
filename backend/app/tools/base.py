from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

class BaseTool(ABC):
    def __init__(self, name: str, description: str, parameters_schema: Dict[str, Any]):
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema

    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """Validate input parameters against the tool's parameter schema."""
        required = self.parameters_schema.get("required", [])
        for req_field in required:
            if req_field not in params or params[req_field] is None:
                raise ValueError(f"Missing required parameter '{req_field}' for tool '{self.name}'.")
        return True

    @abstractmethod
    async def execute(
        self,
        params: Dict[str, Any],
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Execute the tool action and return a structured output dictionary."""
        pass
