import asyncio
import sys
import time

from tests.test_db_models import test_db_operations
from tests.test_auth import test_auth_and_user_flow
from tests.test_event_bus import test_event_bus_and_outbox_flow
from tests.test_integrations import test_integration_layer_flow
from tests.test_context_engine import test_context_engine_flow
from tests.test_agent_framework import test_agent_framework_flow
from tests.test_tool_registry import test_tool_registry_flow
from tests.test_workflow_engine import test_workflow_engine_flow
from tests.test_memory_system import test_memory_system_flow
from tests.test_planning_system import test_planning_system_flow
from tests.test_full_api_suite import test_full_api_suite_flow
from tests.test_realtime_system import test_realtime_system_flow
from tests.test_analytics_prediction import test_analytics_prediction_flow
from tests.test_security_hardening import test_security_hardening_flow
from tests.test_rls_isolation import test_rls_isolation_flow
from tests.test_project_intelligence import test_project_intelligence_flow
from tests.test_oauth_system import test_oauth_system_flow
from tests.test_agent_state_machine import test_agent_state_machine_flow
from tests.test_distributed_lock import test_distributed_lock_flow
from tests.test_circuit_breaker import test_circuit_breaker_flow
from tests.test_prompt_manager import test_prompt_manager_flow
from tests.test_rbac_pdp import test_rbac_pdp_flow
from tests.test_prompt_registry import test_prompt_registry_flow
from tests.test_evaluation_engine import test_evaluation_engine_flow
from tests.test_model_router import test_model_router_flow
from tests.test_cost_monitoring import test_cost_monitoring_flow
from tests.test_memory_lifecycle import test_memory_lifecycle_flow
from tests.test_observability import test_observability_flow
from tests.test_rate_limiter import test_rate_limiter_flow
from tests.test_security_guard import test_security_guard_flow
from tests.test_graph_evolution import test_graph_evolution_flow
from tests.test_tenant_isolation import test_tenant_isolation_flow
from tests.test_frontend_api_contract import test_frontend_api_contract_flow
from tests.test_production_deployment import test_production_deployment_flow
from tests.test_audit_logging import test_audit_logging_flow
from tests.test_role_assignment import test_role_assignment_flow
from tests.test_audit_log_viewer import test_audit_log_viewer_flow
from tests.test_role_management import test_role_management_flow
from tests.test_organization_settings import test_organization_settings_flow
from tests.test_llm_integration import test_llm_integration_flow
from tests.test_real_tool_integrations import test_real_tool_integrations_flow
from tests.test_pgvector_native_search import test_pgvector_native_search_flow
from tests.test_integration_backup_sync import test_integration_backup_sync_flow
from tests.test_repository_linking import test_repository_linking_flow
from tests.test_calendar_sync import test_calendar_sync_flow
from tests.test_slack_channel_mapping import test_slack_channel_mapping_flow
from tests.test_calendar_poller import test_calendar_poller_flow
from tests.test_oauth_token_refresh import test_oauth_token_refresh_flow
from tests.test_jira_projects_list import test_jira_projects_list_flow
from tests.test_integration_realtime_status import test_integration_realtime_status_flow
from tests.test_connection_center_oauth import test_connection_center_oauth_flow
from tests.test_project_task_tenant_isolation import test_project_task_tenant_isolation_flow
from tests.test_analytics_tenant_isolation import test_analytics_tenant_isolation_flow
from tests.test_agent_execution_tenant_isolation import test_agent_execution_tenant_isolation_flow
from tests.test_workflow_execution_tenant_isolation import test_workflow_execution_tenant_isolation_flow
from tests.test_memory_context_tenant_isolation import test_memory_context_tenant_isolation_flow
from tests.test_planning_tenant_isolation import test_planning_tenant_isolation_flow
from tests.test_notifications import test_notifications_flow
from tests.test_recommendations import test_recommendations_flow
from tests.test_event_replay import test_event_replay_flow
from tests.test_project_knowledge_graph import test_project_knowledge_graph_flow
from tests.test_agent_execution_project_ownership import test_agent_execution_project_ownership_flow
from tests.test_integration_audit_logging import test_integration_audit_logging_flow
from tests.test_calendar_meetings_read import test_calendar_meetings_read_flow
from tests.test_recommendation_actions import test_recommendation_actions_flow
from tests.test_organization_invitations import test_organization_invitations_flow
from tests.test_external_identity import test_external_identity_flow
from tests.test_github_discovery_identity import test_github_discovery_identity_flow
from tests.test_jira_identity_resolution import test_jira_identity_resolution_flow
from tests.test_calendar_event_creation import test_calendar_event_creation_flow
from tests.test_slack_discovery import test_slack_discovery_flow

async def run_master_qa_suite():
    print("========================================================================")
    print("        STARTING MASTER REGRESSION QA TEST SUITE (PHASES 1-34)          ")
    print("========================================================================")
    
    start_time = time.time()
    passed_suites = 0
    total_suites = 71

    test_suites = [
        ("Phase 1: Database Foundation", test_db_operations),
        ("Phase 2: Core Backend Framework", test_auth_and_user_flow),
        ("Phase 3: Event System & Outbox Worker", test_event_bus_and_outbox_flow),
        ("Phase 3b: Distributed Lock & Redlock Manager", test_distributed_lock_flow),
        ("Phase 4: Integration Layer Webhooks", test_integration_layer_flow),
        ("Phase 4b: OAuth 2.0 Provider Authorization & Token Encryption", test_oauth_system_flow),
        ("Phase 5: Context Engine & Vector Search", test_context_engine_flow),
        ("Phase 6: AI Agent Framework Personas", test_agent_framework_flow),
        ("Phase 6b: Agent Lifecycle State Machine", test_agent_state_machine_flow),
        ("Phase 6c: LLM Timeout & Circuit Breaker Router", test_circuit_breaker_flow),
        ("Phase 6d: Prompt Context Window Manager & Token Budget Allocator", test_prompt_manager_flow),
        ("Phase 6e: Prompt Versioning, Canary A/B Router & Rollback Engine", test_prompt_registry_flow),
        ("Phase 7: Tool Registry & Execution Logging", test_tool_registry_flow),
        ("Phase 7b: Tool Permission Matrix & RBAC Policy Decision Point", test_rbac_pdp_flow),
        ("Phase 8: Workflow Engine Multi-Agent DAGs", test_workflow_engine_flow),
        ("Phase 8b: Dynamic Model Router & Fallback Engine", test_model_router_flow),
        ("Phase 9: Memory System Vector Recall", test_memory_system_flow),
        ("Phase 9b: AI Cost Monitoring, Accounting & Budget Alert Engine", test_cost_monitoring_flow),
        ("Phase 9c: Memory Lifecycle, Summarization & Automated Vector GC", test_memory_lifecycle_flow),
        ("Phase 10: AI HTN Planning System", test_planning_system_flow),
        ("Phase 11: Full Domain REST APIs", test_full_api_suite_flow),
        ("Phase 13: Real-Time WebSockets Engine", lambda: asyncio.to_thread(test_realtime_system_flow)),
        ("Phase 14: Predictive Analytics Engine", test_analytics_prediction_flow),
        ("Phase 15: Security Hardening & Rate Limits", test_security_hardening_flow),
        ("Phase 15b: Row-Level Security (RLS) Tenant Isolation", test_rls_isolation_flow),
        ("Phase 15c: Multi-Dimensional Rate Limiting Engine & Token Bucket", test_rate_limiter_flow),
        ("Phase 15d: Enterprise Security: Prompt Injection Guard & PII Redaction", test_security_guard_flow),
        ("Phase 15e: Multi-Tenant Schema & Virtual Isolation Engine", test_tenant_isolation_flow),
        ("Phase 16: Project Intelligence Engine Core", test_project_intelligence_flow),
        ("Phase 16b: Knowledge Graph Weight Decay & Event Inference Pipeline", test_graph_evolution_flow),
        ("Phase 17: AI Evaluation & Benchmark Framework", test_evaluation_engine_flow),
        ("Phase 18: OpenTelemetry Distributed Tracing & Telemetry Exporter", test_observability_flow),
        ("Phase 19: Frontend-to-Backend API Contract Integration", test_frontend_api_contract_flow),
        ("Phase 20: Production Deployment Scaffolding (Terraform, k8s, CI/CD)", test_production_deployment_flow),
        ("Phase 21: Audit Logging (append-only security event trail)", test_audit_logging_flow),
        ("Phase 22: Default Role Seeding & RBAC Differentiation", test_role_assignment_flow),
        ("Phase 23: Audit Logs Viewer (RBAC-gated, tenant-isolated)", test_audit_log_viewer_flow),
        ("Phase 24: Role Management (grant/revoke, privilege-escalation guard)", test_role_management_flow),
        ("Phase 25: Organization Settings Console (settings + members, tenant-isolated)", test_organization_settings_flow),
        ("Phase 26: Real LLM Provider Integration (Claude primary, GPT-4o fallback, synthetic last-resort)", test_llm_integration_flow),
        ("Phase 27: Real GitHub/Jira/Slack Tool Execution (not canned responses)", test_real_tool_integrations_flow),
        ("Phase 28: pgvector-Native Similarity Search (query construction + routing)", test_pgvector_native_search_flow),
        ("Phase 29: Jira Backup Delta-Sync Poller (documented 4h backup cron)", test_integration_backup_sync_flow),
        ("Phase 30: GitHub Repository Linking (api_contract.md 4.A, tenant-isolated)", test_repository_linking_flow),
        ("Phase 31: Google Calendar Sync (api_contract.md 7.A, polling-driven primary sync path)", test_calendar_sync_flow),
        ("Phase 32: Slack Channel-to-Project Mapping (api_contract.md 6.A, webhook auto-routing)", test_slack_channel_mapping_flow),
        ("Phase 33: Google Calendar Background Poller (implementation_roadmap.md Milestone 10, 15-min cadence)", test_calendar_poller_flow),
        ("Phase 34: Third-Party OAuth Access-Token Refresh (Google/GitHub/Jira, centralized in get_valid_oauth_token)", test_oauth_token_refresh_flow),
        ("Phase 35: Jira Projects List (api_contract.md 5.A, real REST API v3, paginated)", test_jira_projects_list_flow),
        ("Phase 36: Real-Time Integration Connection Status (implementation_roadmap.md Milestone 6, authenticated WebSocket)", test_integration_realtime_status_flow),
        ("Phase 37: Connection Center OAuth (Slack/Jira/Google Calendar, generic OAuth endpoints)", test_connection_center_oauth_flow),
        ("Phase 38: Project/Task Cross-Tenant Isolation (IDOR fix on workspace_id/project_id trust)", test_project_task_tenant_isolation_flow),
        ("Phase 39: Analytics Cross-Tenant Isolation (Executive Overview dashboard endpoints)", test_analytics_tenant_isolation_flow),
        ("Phase 40: Agent Execution Cross-Tenant Isolation (GET/transition executions IDOR fix)", test_agent_execution_tenant_isolation_flow),
        ("Phase 41: Workflow Execution Cross-Tenant Isolation (GET /workflows/executions IDOR fix)", test_workflow_execution_tenant_isolation_flow),
        ("Phase 42: Memory & Context Cross-Tenant Isolation (client-supplied organization_id IDOR fix, incl. context_search tool)", test_memory_context_tenant_isolation_flow),
        ("Phase 43: Planning Cross-Tenant Isolation (GET /planning/plans & POST /planning/execute plan_id IDOR fix)", test_planning_tenant_isolation_flow),
        ("Phase 44: Notifications API (PUT /notifications/read, api_contract.md section 16.A, per-user tenant isolation)", test_notifications_flow),
        ("Phase 45: Recommendations API (GET /recommendations, api_contract.md section 12.A, persisted via ProjectIntelligenceEngine)", test_recommendations_flow),
        ("Phase 46: Event Bus Replay (POST /events/replay, api_contract.md section 9.A, OrgAdmin-gated, tenant-isolated)", test_event_replay_flow),
        ("Phase 47: Project Unified Knowledge Graph (GET /context/projects/{id}/graph, api_contract.md section 8.A, tenant-isolated)", test_project_knowledge_graph_flow),
        ("Phase 48: IntegrationService Audit Logging Hardening (oauth:connect/disconnect/reauth_required, repository:link, slack:channel_map)", test_integration_audit_logging_flow),
        ("Phase 49: Agent/Workflow Execution Project Ownership (cross-tenant project_id attachment fix in AgentService.execute_agent)", test_agent_execution_project_ownership_flow),
        ("Phase 50: Calendar Meetings Read API (GET /integrations/calendar/meetings, database_schema_design.md section 19, ui_ux_design.md section 10, tenant-isolated)", test_calendar_meetings_read_flow),
        ("Phase 51: Recommendation Actions API (POST /recommendations/{id}/action, implementation_roadmap.md Milestone 15, ui_ux_design.md section 13, tenant-isolated)", test_recommendation_actions_flow),
        ("Phase 52: Organization Creation & Team Invitation (POST /organizations, invitation create/list/revoke/accept, product-vision foundation, tenant-isolated)", test_organization_invitations_flow),
        ("Phase 53: External Identity Foundation (ExternalIdentity model, real Slack auto-link on OAuth connect, unlink, conflict-safe, tenant-isolated)", test_external_identity_flow),
        ("Phase 54: GitHub Repository Discovery & Identity (real /user + /user/repos calls, discover-repositories, linked-repositories, tenant-isolated)", test_github_discovery_identity_flow),
        ("Phase 55: Jira Site & Identity Resolution (real api.atlassian.com/me + accessible-resources calls on OAuth connect, per-org site capture)", test_jira_identity_resolution_flow),
        ("Phase 56: Google Calendar Event Creation (real POST .../events write path, immediate read-back, tenant-isolated)", test_calendar_event_creation_flow),
        ("Phase 57: Slack Channel Discovery (real conversations.list call, discover-channels, mapped-channels, tenant-isolated)", test_slack_discovery_flow),
    ]




















    for name, test_func in test_suites:
        print(f"\n---> Running QA Suite: {name}")
        try:
            if asyncio.iscoroutinefunction(test_func):
                await test_func()
            else:
                res = test_func()
                if asyncio.iscoroutine(res):
                    await res
            passed_suites += 1
            print(f"PASSED: {name}")
        except Exception as e:
            print(f"FAILED: {name} - Exception: {e}")
            import traceback
            traceback.print_exc()

    elapsed = time.time() - start_time
    print("\n========================================================================")
    print(f"        MASTER QA REGRESSION SUMMARY                                    ")
    print(f"        Suites Passed: {passed_suites} / {total_suites}                        ")
    print(f"        Execution Time: {elapsed:.2f} seconds                             ")
    print("========================================================================")

    if passed_suites < total_suites:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_master_qa_suite())
