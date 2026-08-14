from typing import Dict, Any, Optional, Callable
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.registry import get_tool_registry, ToolRegistry
from app.services.tool import ToolService
from app.services.audit import AuditService
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

    async def _audit(
        self,
        db: Optional[AsyncSession],
        organization_id: Optional[uuid.UUID],
        user_id: Optional[uuid.UUID],
        tool_name: str,
        outcome: Dict[str, Any]
    ) -> None:
        """Best-effort audit_logs write for a tool-call outcome. No-op unless the caller
        supplied both a session and an organization_id (tenant context must already be set
        on `db`, e.g. via get_current_user)."""
        if db is None or organization_id is None:
            return
        await AuditService(db).log(
            organization_id=organization_id,
            user_id=user_id,
            action="tool:execute",
            details={"tool_name": tool_name, "status": outcome.get("status"), "error": outcome.get("error")}
        )
        await db.commit()

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        user_role: str = "Developer",
        approval_token: Optional[str] = None,
        agent_execution_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
        organization_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """Validate, check approval via PDP, and execute tool call.

        If `db` is provided, it is reused as-is (the caller is responsible for
        any tenant context already set on it, e.g. via get_current_user). If
        omitted, a fresh session is opened for this call only, matching the
        prior standalone behavior. When `db` and `organization_id` are both
        supplied, every outcome (denied, suspended, not found, invalid, executed)
        is recorded as an audit_logs entry.
        """
        # 1. PDP Check
        if not self.check_permission(tool_name, user_role):
            outcome = {
                "status": "PERMISSION_DENIED",
                "error": f"Role '{user_role}' is not authorized to execute tool '{tool_name}'."
            }
            await self._audit(db, organization_id, user_id, tool_name, outcome)
            return outcome

        # 2. Approval Gate Check
        if self.requires_approval(tool_name) and not approval_token:
            approval_id = str(uuid.uuid4())
            outcome = {
                "status": "WAITING_APPROVAL",
                "approval_id": approval_id,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Execution of side-effect tool '{tool_name}' requires human approval."
            }
            await self._audit(db, organization_id, user_id, tool_name, outcome)
            return outcome

        # 3. Tool Discovery & Parameter Validation
        try:
            tool_instance = self.registry.get_tool(tool_name)
        except KeyError as e:
            outcome = {
                "status": "TOOL_NOT_FOUND",
                "error": str(e)
            }
            await self._audit(db, organization_id, user_id, tool_name, outcome)
            return outcome

        # Tenant identity must come from the authenticated caller, never from a
        # client-supplied tool-call parameter -- same IDOR class already fixed for
        # Projects/Tasks/Analytics/Agent & Workflow executions. Several tools (e.g.
        # context_search, github/slack integration tools) declare "organization_id"
        # as a caller-supplied parameter used to scope data access or resolve OAuth
        # tokens; without this override a caller could pass a different org's UUID
        # here to search/act on another tenant's data via POST /tools/execute even
        # though the direct REST APIs for those same services correctly derive the
        # tenant from current_user. Override rather than reject so legitimate callers
        # that omit the field (or echo their own org back) are unaffected.
        if organization_id is not None and "organization_id" in tool_instance.parameters_schema.get("properties", {}):
            parameters = {**parameters, "organization_id": str(organization_id)}

        is_valid, err_msg = tool_instance.validate_args(parameters)
        if not is_valid:
            outcome = {
                "status": "VALIDATION_FAILED",
                "error": f"Parameter validation error for '{tool_name}': {err_msg}"
            }
            await self._audit(db, organization_id, user_id, tool_name, outcome)
            return outcome

        # 4. Tool Execution & Audit Logging
        parsed_exec_id = uuid.UUID(agent_execution_id) if agent_execution_id else None

        if db is not None:
            tool_service = ToolService(db)
            result = await tool_service.execute_tool(
                tool_name=tool_name,
                parameters=parameters,
                agent_execution_id=parsed_exec_id
            )
        else:
            async with SessionLocal() as fresh_db:
                tool_service = ToolService(fresh_db)
                result = await tool_service.execute_tool(
                    tool_name=tool_name,
                    parameters=parameters,
                    agent_execution_id=parsed_exec_id
                )

        outcome = {
            "status": "SUCCESS" if result.get("status") == "success" else "EXECUTION_ERROR",
            "result": result
        }
        await self._audit(db, organization_id, user_id, tool_name, outcome)
        return outcome

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
