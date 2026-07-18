from typing import Any, Dict, Optional
from app.agents.base import BaseAgent

class RiskManagerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_name="RiskManagerAgent",
            role="Project Risk Manager",
            system_prompt=(
                "You are a Project Risk Manager. Your job is to identify architectural risks, project bottlenecks, "
                "scope creep tendencies, and schedule delays before they impact delivery timelines."
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
            "risk_level": "medium",
            "mitigations": [
                "Schedule mid-sprint sync to realign scope.",
                "Enforce strict secret token checks on public API webhooks."
            ]
        }
