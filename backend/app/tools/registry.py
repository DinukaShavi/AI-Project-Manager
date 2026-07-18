from typing import Any, Dict, List, Optional
from app.tools.base import BaseTool
from app.tools.github_tools import GitHubCreateIssueTool, GitHubGetPRDiffTool
from app.tools.jira_tools import JiraGetIssueTool, JiraUpdateIssueStatusTool
from app.tools.slack_tools import SlackPostMessageTool
from app.tools.context_tools import ContextSearchTool

class ToolRegistry:
    def __init__(self):
        """Central Tool Registry managing tool registration, schema discovery, and execution."""
        self._tools: Dict[str, BaseTool] = {}

    def register_tool(self, tool: BaseTool) -> None:
        """Register an executable tool instance."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool:
        """Fetch tool instance by name."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered in ToolRegistry. Available: {list(self._tools.keys())}")
        return self._tools[name]

    def list_tools(self) -> List[Dict[str, Any]]:
        """List metadata and parameter schemas for all registered tools."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters_schema": tool.parameters_schema
            }
            for tool in self._tools.values()
        ]


_tool_registry_instance: Optional[ToolRegistry] = None

def get_tool_registry() -> ToolRegistry:
    """Singleton getter populating default built-in platform tools."""
    global _tool_registry_instance
    if _tool_registry_instance is None:
        registry = ToolRegistry()
        # Register built-in tools
        registry.register_tool(GitHubCreateIssueTool())
        registry.register_tool(GitHubGetPRDiffTool())
        registry.register_tool(JiraGetIssueTool())
        registry.register_tool(JiraUpdateIssueStatusTool())
        registry.register_tool(SlackPostMessageTool())
        registry.register_tool(ContextSearchTool())
        _tool_registry_instance = registry
    return _tool_registry_instance
