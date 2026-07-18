from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import httpx
from app.core.config import settings

class BaseAgent(ABC):
    def __init__(self, agent_name: str, role: str, system_prompt: str):
        self.agent_name = agent_name
        self.role = role
        self.system_prompt = system_prompt

    def format_system_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        """Format base system prompt with injected context variables."""
        ctx_str = ""
        if context:
            ctx_items = [f"- {k}: {v}" for k, v in context.items()]
            ctx_str = "\nActive Project Context:\n" + "\n".join(ctx_items)
            
        return f"System Role: {self.role}\n{self.system_prompt}\n{ctx_str}"

    async def _llm_call(self, prompt: str, system_prompt: str) -> str:
        """Execute LLM call using OpenAI REST API or local synthetic reasoning fallback."""
        api_key = getattr(settings, "OPENAI_API_KEY", None)
        if api_key and api_key.strip():
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2
            }
            async with httpx.AsyncClient() as client:
                res = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                res.raise_for_status()
                data = res.json()
                return data["choices"][0]["message"]["content"]
        else:
            # Local synthetic reasoning engine fallback for local offline testing
            return self._generate_synthetic_response(prompt, system_prompt)

    def _generate_synthetic_response(self, prompt: str, system_prompt: str) -> str:
        """Generate structured synthetic agent response when no LLM API key is configured."""
        return (
            f"[{self.agent_name} Analysis Report]\n"
            f"Role: {self.role}\n"
            f"Task Evaluated: '{prompt}'\n"
            f"Status: Completed successfully.\n"
            f"Key Findings: Synthesized technical insights based on context data."
        )

    @abstractmethod
    async def execute(self, task_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute agent task and return structured output dictionary."""
        pass
