from typing import Dict, Any, Optional, Callable
import uuid
from app.tools.registry import get_tool_registry, ToolRegistry
from app.services.tool import ToolService
from app.db.session import SessionLocal

from app.core.rbac_pdp import get_pdp, ToolCallAuthorizationRequest, UserRole, RiskLevel

class ToolExecutor:
    """Tool execution engine handling capability matching, Pydantic schema validations, RBAC permissions, approval gates, and Saga rollbacks."""

    HIGH_RISK_SIDE_EFFECT_TOOLS = {
        "merge_pull_request",
        "deploy_release",
        "delete_repository",
        "jira_delete_issue",
        "slack_broadcast_all"
    }

    def __init__(self, registry: Optional[ToolRegistry] = None):
        self.registry = registry or get_tool_registry()
        self.compensation_registry: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self.pdp = get_pdp()

    def requires_approval(self, tool_name: str) -> bool:
        """Check if a tool action requires human-in-the-loop approval."""
        return tool_name in self.HIGH_RISK_SIDE_EFFECT_TOOLS

    def check_permission(self, tool_name: str, user_role: str) -> bool:
        """Evaluate RBAC permissions using PolicyDecisionPoint PDP engine."""
        role_enum = UserRole.DEVELOPER
        try:
            role_enum = UserRole(user_role)
        except ValueError:
            # Map legacy string role names
            role_map = {
                "superadmin": UserRole.SUPER_ADMIN,
                "orgadmin": UserRole.ORG_ADMIN,
                "projectmanager": UserRole.PROJECT_MANAGER,
                "developer": UserRole.DEVELOPER,
                "viewer": UserRole.VIEWER
            }
            role_enum = role_map.get(user_role.lower().replace(" ", "").replace("_", ""), UserRole.DEVELOPER)

        risk = RiskLevel.HIGH if tool_name in self.HIGH_RISK_SIDE_EFFECT_TOOLS else RiskLevel.LOW
        req = ToolCallAuthorizationRequest(
            user_id=str(uuid.uuid4()),
            role=role_enum,
            tool_name=tool_name,
            risk_level=risk
        )
        resp = self.pdp.evaluate_tool_call(req)
        return resp.authorized

    def register_compensation(self, tool_name: str, rollback_func: Callable[[Dict[str, Any]], Any]) -> None:
        """Register a Saga compensating action for a side-effect tool."""
        self.compensation_registry[tool_name] = rollback_func

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        user_role: str = "Developer",
        approval_token: Optional[str] = None,
        agent_execution_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate, check approval via PDP, and execute tool call."""
        # 1. PDP Check
        if not self.check_permission(tool_name, user_role):
            return {
                "status": "PERMISSION_DENIED",
                "error": f"Role '{user_role}' is not authorized to execute tool '{tool_name}'."
            }

        # 2. Approval Gate Check
        if self.requires_approval(tool_name) and not approval_token:
            approval_id = str(uuid.uuid4())
            return {
                "status": "WAITING_APPROVAL",
                "approval_id": approval_id,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Execution of side-effect tool '{tool_name}' requires human approval."
            }

        # 3. Tool Discovery & Parameter Validation
        tool_instance = self.registry.get_tool(tool_name)
        if not tool_instance:
            return {
                "status": "TOOL_NOT_FOUND",
                "error": f"Tool '{tool_name}' is not registered in ToolRegistry."
            }

        is_valid, err_msg = tool_instance.validate_args(parameters)
        if not is_valid:
            return {
                "status": "VALIDATION_FAILED",
                "error": f"Parameter validation error for '{tool_name}': {err_msg}"
            }

        # 4. Tool Execution & Audit Logging
        async with SessionLocal() as db:
            tool_service = ToolService(db)
            parsed_exec_id = uuid.UUID(agent_execution_id) if agent_execution_id else None
            result = await tool_service.execute_tool(
                tool_name=tool_name,
                parameters=parameters,
                agent_execution_id=parsed_exec_id
            )

        return {
            "status": "SUCCESS" if result.get("status") == "success" else "EXECUTION_ERROR",
            "result": result
        }

    async def rollback_step(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Run registered Saga compensating action on step failure."""
        rollback_func = self.compensation_registry.get(tool_name)
        if not rollback_func:
            return {"status": "NO_COMPENSATION_REGISTERED", "tool_name": tool_name}

        try:
            res = await rollback_func(parameters) if callable(rollback_func) else None
            return {"status": "COMPENSATED", "result": res}
        except Exception as ex:
            return {"status": "COMPENSATION_FAILED", "error": str(ex)}
