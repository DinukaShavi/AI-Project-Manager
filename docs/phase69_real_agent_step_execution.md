# Phase 69 Plan: Real Agent Step Execution Grounded in Real Context

**Status:** Implemented and verified. 3/3 feature checks passing standalone; 82/82 master
regression suite passing (including the pre-existing `test_project_intelligence.py`, which
transparently now exercises the real path via its HTTP endpoint test, and still passes its
dedicated no-db-session test unchanged). Roadmap Step 7 (audit Phase H), scoped narrowly — see
"Split from Step 7" below.

## What's already there, re-verified

`ProjectIntelligenceEngine.process_goal`'s Stage 3 loop branches on `step.step_type`:
`"tool"` steps go through the real `ToolExecutor` (real Jira/GitHub/Slack calls). Every other
step (`step_type="agent"` — the only other value `HTNPlanner` ever produces) returns a
hardcoded dict: `"analysis": f"Synthetic reasoning analysis completed for {step.name}."` —
never touches an LLM, never touches retrieved context, regardless of `self.db` or the real
`subgraph_context` already loaded one line above it.

Investigated whether real infrastructure already exists to replace this, rather than building
something new:

- **A real, separate LLM execution path already exists**: `POST /agents/execute` →
  `AgentService.execute_agent` → `agent.execute(task_input, context)` →
  `BaseAgent._llm_call` (real Claude/GPT-4o failover via `ModelRouter` + circuit breakers,
  Phase 26). `execute_agent` also persists a real, queryable `AgentExecution` row per call and
  drives it through the real `AgentStateMachine`.
- **`context` is already a real, budget-managed prompt-injection mechanism**:
  `BaseAgent.format_system_prompt(context)` stringifies a `context` dict into
  `PromptContextItem`s assembled via `get_prompt_manager()` — already built (Phase 6d), just
  never fed anything from `process_goal` today.
- **The planner's `target` values already match `AgentService.get_agent`'s aliases exactly**
  (`tpm`, `code_analyst`, `risk_manager`, `architect`) — no mapping layer needed.

Decision: **reuse this existing real path**, not build a second one — matches the standing
"reuse existing architecture" rule, and the fact that `POST /agents/execute` and
`POST /planning/intelligence` producing two different kinds of "agent execution" (one real,
one templated) for what's conceptually the same action was itself part of the problem.

## Split from Step 7

The roadmap's Step 7 bundled two different things: (a) making agent *step execution* real,
and (b) making *plan decomposition* (`HTNPlanner.decompose_goal`'s keyword-matched templates
— "sprint" → these 4 fixed steps, etc.) real/dynamic. (b) is a materially larger, riskier
undertaking (LLM-driven plan generation, output parsing into validated `PlanStep` DAGs,
failure/injection handling) that deserves its own design pass, not a rider on this turn. This
phase scopes to (a) only — **which steps get planned stays keyword-templated for now; how
each "agent" step actually executes becomes real.**

## Design

- **`ProjectIntelligenceEngine.process_goal`**, Stage 3 loop: when `step.step_type != "tool"`
  **and `self.db` is not None**, call the real
  `AgentService(self.db).execute_agent(agent_type=step.target, task_input=..., organization_id=...,
  project_id=..., context=real_context)` instead of the synthetic dict. When `self.db` is
  `None` (the existing no-db unit-test path, `test_project_intelligence.py`), the synthetic
  dict is kept as a graceful fallback — mirrors the exact guard already used for graph loading
  (`if self.db and project_id:`) one stage earlier; not a new shortcut, an existing pattern.
- **`real_context` assembled from three already-real sources**, all previously computed-but-
  unused or one call away:
  - `subgraph_context` (already loaded via `self.graph.get_subgraph_context`, currently only
    forwarded to the planner, which ignores it) — real graph bottleneck/relationship data.
  - The project's latest `ContextSnapshot.state_payload["summary"]` (Phase 68), if one exists.
  - Real semantic search over indexed `ContextChunk`s for this specific step's task text —
    `ContextEngineService.search_context(organization_id, query_text=step.input_params["task"],
    project_id, top_k=3)` (Phase 58).
- **Result shape preserved** for the downstream reflection/replan/executed_steps contract
  (`ReflectionEngine.evaluate_step_output` reads `status`/`result`): the real
  `AgentExecution.output_payload` becomes `tool_res["result"]`, with `tool_res["status"]`
  mapped from the execution's final state (`"SUCCESS"` on `COMPLETED`, `"FAILURE"`
  otherwise) — same vocabulary the synthetic path already used, so reflection/replan logic
  doesn't need to change.
- **When no LLM key is configured** (this sandboxed dev environment today), `_llm_call`
  already falls back to each persona's own pre-existing, honestly-labeled
  `_generate_synthetic_response` — a real, tested, *different* fallback than the one being
  removed here (per-persona, contextual, already shipped) — not something this phase
  introduces.

## Explicitly out of scope for this turn

- `HTNPlanner.decompose_goal` staying keyword-template-based (Step 7b, future, separate
  design pass — LLM-driven decomposition).
- `TechnicalPMAgent.execute` (and the other three personas) return a hardcoded
  `"recommendations"` list alongside the real `"analysis"` field — found during investigation,
  pre-existing, adjacent but separate from what this phase touches (agent *invocation* from
  planning, not agent *implementation*). Worth its own look later.

## Files expected to change

- `backend/app/services/intelligence_engine.py` — real execution branch, real context
  assembly.
- `backend/tests/test_real_agent_step_execution.py` (new) — real DB session,
  real `AgentExecution` rows created per step, real context assembled and passed, reflection/
  replan contract preserved. Does not mock the LLM boundary (no API key configured in this
  environment, so `_llm_call` naturally exercises its own already-tested synthetic fallback —
  consistent with how this phase treats that fallback as pre-existing, not newly introduced).
- `backend/tests/run_all_tests.py` — register Phase 69.
- `test_project_intelligence.py` — unchanged (still exercises the no-db path deliberately).

## Test plan

- A real `POST /planning/intelligence` run with a real `db` session produces one real,
  queryable `AgentExecution` row per non-tool plan step (verified via `GET
  /agents/executions/{id}`), not a synthetic inline dict.
- The `context` passed into `execute_agent` contains real assembled data (subgraph, snapshot
  summary if present, semantic search results) — not empty, not fabricated.
- The no-db path (`ProjectIntelligenceEngine()` with no session) still returns the synthetic
  fallback unchanged — proves the existing unit test's contract is preserved deliberately, not
  accidentally broken.
- Reflection/replan logic still functions correctly against real `AgentExecution` output
  (status mapping verified).
- Master suite stays green (82/82 expected).
