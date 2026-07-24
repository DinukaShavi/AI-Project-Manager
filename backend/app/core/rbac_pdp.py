import uuid
from enum import Enum
from typing import Dict, Set, Optional, Any
from pydantic import BaseModel, Field

class UserRole(str, Enum):
    SUPER_ADMIN = "SuperAdmin"
    ORG_ADMIN = "OrgAdmin"
    PROJECT_MANAGER = "ProjectManager"
    DEVELOPER = "Developer"
    VIEWER = "Viewer"

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class ToolCallAuthorizationRequest(BaseModel):
    user_id: str
    role: UserRole
    tool_name: str
    target_resource_urn: Optional[str] = None
    risk_level: RiskLevel = RiskLevel.LOW

class ToolCallAuthorizationResponse(BaseModel):
    authorized: bool
    approval_required: bool
    approval_policy: str
    reason: str

# Tool Permission Matrix Mapping according to Enterprise Architecture Spec Section 5
# Tool -> Allowed Roles
TOOL_ROLE_MATRIX: Dict[str, Set[UserRole]] = {
    "delete_repository": {UserRole.SUPER_ADMIN},
    "merge_pull_request": {UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.PROJECT_MANAGER, UserRole.DEVELOPER},
    "create_jira_ticket": {UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.PROJECT_MANAGER, UserRole.DEVELOPER},
    "deploy_release": {UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.PROJECT_MANAGER},
    "send_slack_broadcast": {UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.PROJECT_MANAGER, UserRole.DEVELOPER},
    "modify_prompt": {UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN},
}

# Approval Policies Mapping
TOOL_APPROVAL_POLICIES: Dict[str, Dict[str, Any]] = {
    "delete_repository": {"approval_required": True, "policy": "Requires Super Admin validation"},
    "merge_pull_request": {"approval_required": False, "policy": "PM approval required if CI fails"},
    "create_jira_ticket": {"approval_required": False, "policy": "Auto-executed"},
    "deploy_release": {"approval_required": True, "policy": "PM validation required"},
    "send_slack_broadcast": {"approval_required": False, "policy": "Auto-executed"},
    "modify_prompt": {"approval_required": False, "policy": "Audit log recorded"},
}

class PolicyDecisionPoint:
    """Policy Decision Point (PDP) evaluating role-based tool execution paths and approval gates."""

    def __init__(self):
        self.matrix = TOOL_ROLE_MATRIX.copy()
        self.approval_policies = TOOL_APPROVAL_POLICIES.copy()

    def evaluate_tool_call(self, request: ToolCallAuthorizationRequest) -> ToolCallAuthorizationResponse:
        tool_name = request.tool_name.lower()
        user_role = request.role

        # 1. Check Matrix Authorization
        allowed_roles = self.matrix.get(tool_name)
        if allowed_roles is not None:
            is_authorized = user_role in allowed_roles
        else:
            # Default policy for custom unregistered tools: Allowed for non-viewers
            is_authorized = user_role != UserRole.VIEWER

        if not is_authorized:
            return ToolCallAuthorizationResponse(
                authorized=False,
                approval_required=False,
                approval_policy="Access Denied",
                reason=f"Role '{user_role.value}' is not authorized to execute tool '{request.tool_name}'."
            )

        # 2. Check Approval Policies & Risk Level Escalation
        policy_info = self.approval_policies.get(tool_name, {"approval_required": False, "policy": "Auto-executed"})
        approval_req = policy_info["approval_required"]
        approval_pol = policy_info["policy"]

        # Escalate high/critical risk levels to mandatory human-in-the-loop approval
        if request.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) and not approval_req:
            approval_req = True
            approval_pol = f"Mandatory approval required for {request.risk_level.value} risk action."

        return ToolCallAuthorizationResponse(
            authorized=True,
            approval_required=approval_req,
            approval_policy=approval_pol,
            reason=f"Role '{user_role.value}' is authorized to execute '{request.tool_name}' ({approval_pol})."
        )


# Singleton Instance Manager
_pdp_instance: Optional[PolicyDecisionPoint] = None

def get_pdp() -> PolicyDecisionPoint:
    """Get global PolicyDecisionPoint singleton instance."""
    global _pdp_instance
    if _pdp_instance is None:
        _pdp_instance = PolicyDecisionPoint()
    return _pdp_instance
