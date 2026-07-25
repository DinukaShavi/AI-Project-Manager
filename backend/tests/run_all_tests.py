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

async def run_master_qa_suite():
    print("========================================================================")
    print("        STARTING MASTER REGRESSION QA TEST SUITE (PHASES 1-33)          ")
    print("========================================================================")
    
    start_time = time.time()
    passed_suites = 0
    total_suites = 33

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
