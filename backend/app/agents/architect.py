from typing import Any, Dict, Optional
from app.agents.base import BaseAgent

class ArchitectureReviewerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_name="ArchitectureReviewerAgent",
            role="System Architect",
            system_prompt=(
                "You are a System Architect. Your job is to review system design proposals, API contract integrity, "
                "database schema normalization, and Clean Architecture boundaries."
            )
        )

    async def execute(self, task_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        full_sys_prompt = self.format_system_prompt(context)
        llm_response = await self._llm_call(task_input, full_sys_prompt)
        
        return {
            "agent": self.agent_name,
            "role": self.role,
            "task": task_input,
            "analysis": llm_response,
            "architecture_score": 96.0,
            "recommendations": [
                "Maintain decoupling between domain entities and REST API DTOs.",
                "Ensure event outbox pattern handles transaction retries."
            ]
        }
