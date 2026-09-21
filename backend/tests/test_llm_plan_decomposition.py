import asyncio

from app.planning.planner import HTNPlanner, PlanStep


VALID_PLAN_JSON = """```json
[
  {"step_id": "s1", "name": "Analyze sprint velocity", "step_type": "agent", "target": "tpm",
   "input_params": {"task": "Analyze current sprint velocity and task status"}, "depends_on": []},
  {"step_id": "s2", "name": "Notify team", "step_type": "tool", "target": "slack_post_message",
   "input_params": {"organization_id": "org-123", "channel": "#dev", "message": "Sprint audit complete"},
   "depends_on": ["s1"]}
]
```"""

VALID_PLAN_JSON_UNFENCED = (
    '[{"step_id": "only", "name": "Review architecture", "step_type": "agent", '
    '"target": "architect", "input_params": {"task": "Review system design"}, "depends_on": []}]'
)

UNKNOWN_AGENT_JSON = (
    '[{"step_id": "s1", "name": "x", "step_type": "agent", "target": "SprintPlanningAgent", '
    '"input_params": {}, "depends_on": []}]'
)

UNKNOWN_TOOL_JSON = (
    '[{"step_id": "s1", "name": "x", "step_type": "tool", "target": "delete_everything", '
    '"input_params": {}, "depends_on": []}]'
)

INVALID_TOOL_PARAMS_JSON = (
    '[{"step_id": "s1", "name": "x", "step_type": "tool", "target": "slack_post_message", '
    '"input_params": {"channel": "#dev"}, "depends_on": []}]'
)

CYCLIC_JSON = (
    '[{"step_id": "a", "name": "A", "step_type": "agent", "target": "tpm", "input_params": {}, "depends_on": ["b"]},'
    ' {"step_id": "b", "name": "B", "step_type": "agent", "target": "tpm", "input_params": {}, "depends_on": ["a"]}]'
)

DANGLING_DEP_JSON = (
    '[{"step_id": "a", "name": "A", "step_type": "agent", "target": "tpm", "input_params": {}, "depends_on": ["ghost"]}]'
)

NON_JSON_TEXT = "Sure, here is a plan for your sprint: first, review velocity, then notify the team."


def _patch_llm(planner: HTNPlanner, canned_response: str) -> None:
    async def fake_llm_call(prompt, system_prompt, task_category="output_reflection"):
        return canned_response
    planner._planner_llm._llm_call = fake_llm_call


async def test_llm_plan_decomposition_flow():
    print("Initializing LLM Plan Decomposition (Phase 71) validation tests...")

    # 1. In this sandboxed environment (no LLM API keys configured), decompose_goal_async
    #    must transparently reproduce decompose_goal's exact deterministic output -- proves
    #    the fallback tier is exact, not a silently different behavior.
    print("\nTest 1: Verifying decompose_goal_async falls back to the exact template plan when unconfigured...")
    planner = HTNPlanner()
    goal = "Audit sprint delivery health"
    sync_steps = planner.decompose_goal(goal)
    async_steps = await planner.decompose_goal_async(goal)
    assert len(async_steps) == len(sync_steps)
    for s, a in zip(sync_steps, async_steps):
        assert s.step_id == a.step_id and s.target == a.target and s.step_type == a.step_type
    print(f"SUCCESS: decompose_goal_async reproduced the {len(sync_steps)}-step template plan exactly.")

    # 2. A valid, fenced LLM JSON plan is accepted and correctly parsed.
    print("\nTest 2: Verifying a valid fenced JSON plan is accepted...")
    _patch_llm(planner, VALID_PLAN_JSON)
    steps = await planner.decompose_goal_async("Whatever goal")
    assert len(steps) == 2
    assert steps[0].step_id == "s1" and steps[0].target == "tpm" and steps[0].step_type == "agent"
    assert steps[1].step_id == "s2" and steps[1].target == "slack_post_message" and steps[1].step_type == "tool"
    assert steps[1].depends_on == ["s1"]
    print("SUCCESS: Valid fenced LLM plan parsed into real PlanStep objects.")

    # 3. A valid, unfenced single-step JSON plan is also accepted.
    print("\nTest 3: Verifying a valid unfenced JSON plan is accepted...")
    _patch_llm(planner, VALID_PLAN_JSON_UNFENCED)
    steps = await planner.decompose_goal_async("Whatever goal")
    assert len(steps) == 1 and steps[0].target == "architect"
    print("SUCCESS: Valid unfenced LLM plan parsed correctly.")

    # 4-9. Every invalid shape falls back to the deterministic template instead of reaching
    #      execution -- proves _decompose_with_llm rejects each specific failure mode, and
    #      decompose_goal_async never lets an invalid plan through.
    invalid_cases = [
        ("unknown agent target", UNKNOWN_AGENT_JSON),
        ("unknown tool target", UNKNOWN_TOOL_JSON),
        ("tool step with invalid/missing params", INVALID_TOOL_PARAMS_JSON),
        ("cyclic dependency", CYCLIC_JSON),
        ("dangling dependency reference", DANGLING_DEP_JSON),
        ("non-JSON prose response", NON_JSON_TEXT),
    ]
    print("\nTest 4: Verifying every invalid LLM plan shape falls back to the template plan...")
    for i, (label, canned) in enumerate(invalid_cases, start=4):
        _patch_llm(planner, canned)
        fallback_goal = "Audit sprint delivery health"
        expected = planner.decompose_goal(fallback_goal)
        actual = await planner.decompose_goal_async(fallback_goal)
        assert len(actual) == len(expected) and all(a.step_id == e.step_id for a, e in zip(actual, expected)), (
            f"Case '{label}' did not fall back to the template plan as expected."
        )
        # Also verify _decompose_with_llm itself raises (not decompose_goal_async silently
        # returning the template for an unrelated reason).
        raised = False
        try:
            await planner._decompose_with_llm(fallback_goal, None)
        except Exception:
            raised = True
        assert raised, f"Case '{label}' should have raised inside _decompose_with_llm."
        print(f"  [{label}] correctly rejected -> fell back to template.")
    print("SUCCESS: All invalid LLM plan shapes correctly rejected and fell back to the template plan.")

    # 10. The two real call sites (ProjectIntelligenceEngine, PlanningService) both now use
    #     decompose_goal_async -- verified by source inspection is fragile across refactors,
    #     so instead re-run a real process_goal call end-to-end (no db session, matching the
    #     existing no-db unit-test contract) and confirm it still returns a well-formed result
    #     using the new async decomposition path without error.
    print("\nTest 5: Verifying ProjectIntelligenceEngine.process_goal still works end-to-end via the new async path...")
    from app.services.intelligence_engine import ProjectIntelligenceEngine
    import uuid
    engine = ProjectIntelligenceEngine()
    result = await engine.process_goal(
        goal="Audit sprint delivery health",
        organization_id=str(uuid.uuid4()),
        user_role="Developer",
    )
    assert "plan_execution" in result and result["plan_execution"]["total_steps"] > 0
    print("SUCCESS: process_goal completed end-to-end via decompose_goal_async.")

    print("\nAll LLM Plan Decomposition tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_llm_plan_decomposition_flow())
