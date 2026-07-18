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

async def run_master_qa_suite():
    print("========================================================================")
    print("        STARTING MASTER REGRESSION QA TEST SUITE (PHASES 1-15)          ")
    print("========================================================================")
    
    start_time = time.time()
    passed_suites = 0
    total_suites = 14

    test_suites = [
        ("Phase 1: Database Foundation", test_db_operations),
        ("Phase 2: Core Backend Framework", test_auth_and_user_flow),
        ("Phase 3: Event System & Outbox Worker", test_event_bus_and_outbox_flow),
        ("Phase 4: Integration Layer Webhooks", test_integration_layer_flow),
        ("Phase 5: Context Engine & Vector Search", test_context_engine_flow),
        ("Phase 6: AI Agent Framework Personas", test_agent_framework_flow),
        ("Phase 7: Tool Registry & Execution Logging", test_tool_registry_flow),
        ("Phase 8: Workflow Engine Multi-Agent DAGs", test_workflow_engine_flow),
        ("Phase 9: Memory System Vector Recall", test_memory_system_flow),
        ("Phase 10: AI HTN Planning System", test_planning_system_flow),
        ("Phase 11: Full Domain REST APIs", test_full_api_suite_flow),
        ("Phase 13: Real-Time WebSockets Engine", lambda: asyncio.to_thread(test_realtime_system_flow)),
        ("Phase 14: Predictive Analytics Engine", test_analytics_prediction_flow),
        ("Phase 15: Security Hardening & Rate Limits", test_security_hardening_flow),
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
