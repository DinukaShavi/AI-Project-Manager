# Phase 71 Plan: Real LLM-Driven Plan Decomposition (Step 7b)

**Status:** Implemented and verified. 5/5 feature checks passing standalone; 83/83 master
regression suite passing (`test_planning_system.py` and `test_project_intelligence.py`, both
pre-existing and unmodified, keep passing with their original template-plan step-count
assertions intact, since the fallback in this key-less environment reproduces
`decompose_goal`'s output exactly). Also fixed a pre-existing off-by-one in
`run_all_tests.py`'s summary line (`total_suites` was a hand-maintained literal that had
drifted one behind the real list even before this phase; replaced with `len(test_suites)` so
it can't drift again). Closes the last item the readiness-check audit named as a remaining gap
in the AI layer: "which steps run" was still keyword-templated even though Phase 69 made "how
each step executes" real.

## What's already there, re-verified

`HTNPlanner.decompose_goal` (`backend/app/planning/planner.py`) matches the goal string against
`"sprint"/"release"`, `"architecture"/"design"/"audit"`, or a generic fallback, and returns one
of three fixed `PlanStep` lists every time -- no LLM call, no project-specific reasoning. Two
real, separate call sites depend on it: `ProjectIntelligenceEngine.process_goal`
(`intelligence_engine.py:48`, reflection/replan/Monte-Carlo pipeline, Phase 69's real grounded
step execution) and `PlanningService.generate_plan` (`services/planning.py:25`, persists an
`AgentPlan` row and executes it via the real `WorkflowExecutor`).

Investigated whether real infrastructure already exists for this, rather than building
something new -- it does, unused, same pattern as `ContextSnapshot` before Phase 68 and
`RedisEventBus.subscribe` before Phase 58:

- **`ModelRouter.ROUTING_MATRIX` already has a `DAG_GENERATION` route**
  (`app/core/model_router.py:27-34`), primary Claude 3.5 Sonnet / fallback GPT-4o, documented
  reason: "Requires complex HTN reasoning and strict JSON schema output." Provisioned since the
  router was built, never once selected by any real call before this phase.
- **`BaseAgent._llm_call`** (Phase 26/69) already provides the real Claude/GPT-4o failover +
  circuit-breaker + honest-fallback plumbing this needs -- no new provider-calling code
  required, same pattern Phase 69 reused for step execution.
- **`ToolExecutor`'s RBAC/approval/tenant-scoping gates already apply unconditionally** to every
  tool-type step regardless of who authored the plan (a human, the keyword template, or this
  LLM path) -- so LLM-authored tool steps don't need a new safety layer, only decompose-time
  parameter validation to keep a malformed step from ever reaching execution.

Decision: **reuse both**, not build a second LLM-calling path or a second tool-safety model.

## Design

- **`HTNPlanner.decompose_goal` (sync, keyword-template) is left completely unchanged** -- it's
  still the deterministic domain-method logic, and now serves double duty as both a legitimate
  planning strategy on its own and the honest fallback for the new path. Existing tests that
  call it directly (`test_planning_system.py`, `test_project_intelligence.py`) needed zero
  changes.
- **New `HTNPlanner.decompose_goal_async(goal, context)`** is what both real call sites now
  await instead. It:
  1. Builds a prompt listing the 4 real agent personas (`tpm`, `code_analyst`, `risk_manager`,
     `architect` -- exactly `AgentService.get_agent`'s alias set) and the 6 real registered
     tools with their live parameter schemas (`get_tool_registry().list_tools()`), plus a
     truncated JSON snippet of the real project subgraph context when one was passed in.
  2. Calls `_PlannerLLM._llm_call` (a `BaseAgent` subclass that exists purely to reuse
     `_llm_call`'s real infrastructure; `task_category="dag_generation"`) asking for a JSON
     array of 2-6 steps.
  3. Parses and validates every step before accepting the plan: unique non-empty `step_id`;
     `step_type` is `"agent"` or `"tool"`; an `"agent"` step's `target` is one of the 4 real
     aliases; a `"tool"` step's `target` is a real registered tool name AND its `input_params`
     pass that tool's own real `validate_args` schema check (`app/tools/base.py:19-25`) --
     the same check `ToolExecutor.execute_tool` would run at execution time, just run earlier
     so a malformed LLM tool call never reaches a live workflow; the whole step list is then
     run through the existing `build_dag_from_plan` -> `WorkflowDAG.validate_dag`, which already
     rejects cycles and dangling dependency references.
  4. **Any failure at any point -- unconfigured keys, network/provider failure, non-JSON
     response, an unrecognized agent/tool target, invalid tool params, a cyclic or dangling
     DAG -- falls back to `decompose_goal(goal, context)` (the unchanged keyword-template
     path), never a crash and never a half-valid plan reaching execution.** This includes the
     specific case of `_llm_call` itself falling back to `_generate_synthetic_response` when no
     provider is configured: that text isn't valid JSON, so it fails parsing and falls through
     to the template exactly like any other failure -- not a special case, the same tier
     `_llm_call` already uses internally (Claude -> GPT-4o -> synthetic text) just extended one
     level further (synthetic text -> keyword template) for this specific caller.
- **`ProjectIntelligenceEngine.process_goal`** (`intelligence_engine.py:48`) and
  **`PlanningService.generate_plan`** (`services/planning.py:25`) both switched from
  `self.planner.decompose_goal(...)` to `await self.planner.decompose_goal_async(...)` --
  one-line changes each, no other logic in either method needed to change since `PlanStep`'s
  shape and downstream consumption (reflection, replan, `AgentPlan` persistence,
  `build_dag_from_plan`) are identical either way.

## Why this doesn't weaken tool-call safety

An LLM-authored plan is not a new privileged path. A `"tool"` step's real execution --
`ToolExecutor.execute_tool` -- still runs the same RBAC permission check, the same
high-risk-tool approval gate, and the same tenant scoping regardless of whether the step came
from a human, the keyword template, or the LLM. This phase only adds decompose-time parameter
validation so a malformed LLM tool call fails fast (falls back to the template) instead of
reaching `WorkflowExecutor`, which would otherwise halt the entire DAG on a bad tool call
(`workflows/executor.py:93-100`) -- a robustness improvement, not a new trust boundary.

## Explicitly out of scope for this turn

- Changing what `decompose_goal` (sync) does -- it remains the deterministic domain-method
  planner, unchanged, and is now also the designed fallback.
- Any change to `WorkflowExecutor`, `ToolExecutor`, or `ReflectionEngine` -- none needed; a
  `PlanStep` produced by the LLM path is indistinguishable in shape from one produced by the
  template path by the time either reaches execution.

## Files changed

- `backend/app/planning/planner.py` -- `_PlannerLLM`, `AGENT_PERSONAS`, `decompose_goal_async`,
  `_decompose_with_llm`, `_extract_json_array`.
- `backend/app/services/intelligence_engine.py` -- one-line call-site change.
- `backend/app/services/planning.py` -- one-line call-site change.
- `backend/tests/test_llm_plan_decomposition.py` (new).
- `backend/tests/run_all_tests.py` -- register Phase 71.

## Test plan

No LLM API keys are configured in this sandboxed environment, so end-to-end "the LLM actually
returns a usable plan" cannot be exercised live here -- the same limitation Phase 69 already
documented for its own real-execution tests. Two-tier verification instead:

1. **Fallback correctness (live, no mocks):** `decompose_goal_async` for a real goal in this
   environment (no keys configured) produces a plan identical to `decompose_goal`'s deterministic
   output for the same goal -- proves the fallback is exact and transparent, not a silently
   different behavior.
2. **Validation logic (isolated, deterministic):** `_PlannerLLM._llm_call` is monkeypatched to
   return specific canned strings -- a valid JSON plan (fenced and unfenced), an unknown agent
   target, an unknown tool target, a tool step with invalid params, a cyclic dependency, a
   dangling dependency reference, and non-JSON text -- asserting the valid plan is accepted
   as-is and every invalid case correctly falls back to the template, exercising every branch
   of `_decompose_with_llm` without needing a real network call or API key.
3. Existing suites (`test_planning_system.py`, `test_project_intelligence.py`) are expected to
   keep passing unmodified, since the fallback in this key-less environment reproduces their
   exact previously-asserted step counts.
