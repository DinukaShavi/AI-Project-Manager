from typing import Any, Dict, Optional
from app.agents.base import BaseAgent

class TechnicalPMAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_name="TechnicalPMAgent",
            role="Technical Project Manager",
            system_prompt=(
                "You are an expert Technical Project Manager. Your job is to analyze sprint progress, "
                "break down requirements into technical task assignments, estimate developer velocity, "
                "and resolve project blockers."
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
            "recommendations": [
                "Verify sprint milestone deadlines.",
                "Assign high-priority blockers to lead engineers."
            ]
        }
