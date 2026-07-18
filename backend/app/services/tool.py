from typing import Any, Dict, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.registry import get_tool_registry
from app.models.agent import ToolExecution

class ToolService:
    def __init__(self, session: AsyncSession):
        """Tool Service managing tool discovery, parameter validations, execution, and audit logging."""
        self.session = session
        self.registry = get_tool_registry()

    def list_available_tools(self) -> List[Dict[str, Any]]:
        """Return list of all registered tools and their parameter schemas."""
        return self.registry.list_tools()

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        agent_execution_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Execute a tool by name and log execution status in database if agent context is present."""
        tool = self.registry.get_tool(tool_name)
        
        status_flag = "success"
        error_msg = None
        result = {}
        
        try:
            result = await tool.execute(parameters, session=self.session)
        except Exception as e:
            status_flag = "failure"
            error_msg = str(e)
            result = {"status": "error", "message": error_msg}

        # Log tool execution in database if linked to an agent execution
        if agent_execution_id:
            tool_exec = ToolExecution(
                agent_execution_id=agent_execution_id,
                tool_name=tool_name,
                tool_parameters=parameters,
                tool_output=result,
                status=status_flag,
                error_message=error_msg
            )
            self.session.add(tool_exec)
            await self.session.commit()

        if status_flag == "failure":
            raise ValueError(f"Tool '{tool_name}' execution failed: {error_msg}")

        return result
