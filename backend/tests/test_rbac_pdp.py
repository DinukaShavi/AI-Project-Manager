import asyncio
import uuid
from app.core.rbac_pdp import (
    get_pdp,
    PolicyDecisionPoint,
    ToolCallAuthorizationRequest,
    UserRole,
    RiskLevel
)

async def test_rbac_pdp_flow():
    print("Initializing Tool Permission Matrix & RBAC PDP validation tests...")
    pdp = get_pdp()
    test_user_id = str(uuid.uuid4())

    # 1. Test delete_repository (SuperAdmin ONLY)
    print("\nTest 1: Testing delete_repository role permissions (SuperAdmin ONLY)...")
    req_super = ToolCallAuthorizationRequest(user_id=test_user_id, role=UserRole.SUPER_ADMIN, tool_name="delete_repository", risk_level=RiskLevel.CRITICAL)
    res_super = pdp.evaluate_tool_call(req_super)
    assert res_super.authorized is True
    assert res_super.approval_required is True

    req_org = ToolCallAuthorizationRequest(user_id=test_user_id, role=UserRole.ORG_ADMIN, tool_name="delete_repository", risk_level=RiskLevel.CRITICAL)
    res_org = pdp.evaluate_tool_call(req_org)
    assert res_org.authorized is False

    req_dev = ToolCallAuthorizationRequest(user_id=test_user_id, role=UserRole.DEVELOPER, tool_name="delete_repository", risk_level=RiskLevel.CRITICAL)
    res_dev = pdp.evaluate_tool_call(req_dev)
    assert res_dev.authorized is False
    print("SUCCESS: delete_repository restricted to SuperAdmin with mandatory approval.")

    # 2. Test deploy_release (SuperAdmin, OrgAdmin, PM allowed; Developer denied)
    print("\nTest 2: Testing deploy_release role permissions...")
    req_pm = ToolCallAuthorizationRequest(user_id=test_user_id, role=UserRole.PROJECT_MANAGER, tool_name="deploy_release", risk_level=RiskLevel.HIGH)
    res_pm = pdp.evaluate_tool_call(req_pm)
    assert res_pm.authorized is True
    assert res_pm.approval_required is True

    req_dev_deploy = ToolCallAuthorizationRequest(user_id=test_user_id, role=UserRole.DEVELOPER, tool_name="deploy_release", risk_level=RiskLevel.HIGH)
    res_dev_deploy = pdp.evaluate_tool_call(req_dev_deploy)
    assert res_dev_deploy.authorized is False
    print("SUCCESS: deploy_release allowed for PM, denied for Developer.")

    # 3. Test modify_prompt (SuperAdmin, OrgAdmin allowed; PM denied)
    print("\nTest 3: Testing modify_prompt role permissions...")
    req_org_prompt = ToolCallAuthorizationRequest(user_id=test_user_id, role=UserRole.ORG_ADMIN, tool_name="modify_prompt", risk_level=RiskLevel.MEDIUM)
    res_org_prompt = pdp.evaluate_tool_call(req_org_prompt)
    assert res_org_prompt.authorized is True

    req_pm_prompt = ToolCallAuthorizationRequest(user_id=test_user_id, role=UserRole.PROJECT_MANAGER, tool_name="modify_prompt", risk_level=RiskLevel.MEDIUM)
    res_pm_prompt = pdp.evaluate_tool_call(req_pm_prompt)
    assert res_pm_prompt.authorized is False
    print("SUCCESS: modify_prompt allowed for OrgAdmin, denied for PM.")

    # 4. Test Viewer Role Denied Across Side-Effect Tools
    print("\nTest 4: Testing Viewer role restrictions...")
    req_viewer = ToolCallAuthorizationRequest(user_id=test_user_id, role=UserRole.VIEWER, tool_name="create_jira_ticket", risk_level=RiskLevel.LOW)
    res_viewer = pdp.evaluate_tool_call(req_viewer)
    assert res_viewer.authorized is False
    print("SUCCESS: Viewer role denied write/tool execution paths.")

    print("\nAll Tool Permission Matrix & RBAC PDP tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_rbac_pdp_flow())
