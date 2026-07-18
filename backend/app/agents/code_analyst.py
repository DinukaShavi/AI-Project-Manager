from typing import Any, Dict, Optional
from app.agents.base import BaseAgent

class CodeAnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_name="CodeAnalystAgent",
            role="Senior Code Analyst & Reviewer",
            system_prompt=(
                "You are a Senior Code Analyst. Your job is to inspect pull requests, evaluate code diffs, "
                "detect potential bugs or performance bottlenecks, and ensure test coverage standards."
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
            "code_quality_score": 92.5,
            "action_items": [
                "Ensure async database sessions are closed in exception blocks.",
                "Verify automated test coverage for edge cases."
            ]
        }
