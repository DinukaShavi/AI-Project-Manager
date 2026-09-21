# Phase 82 Plan: Real Reranking on the Agent-Grounding Search

**Status:** Implemented and verified. Extended `test_real_agent_step_execution.py` to wrap
(not replace) the real `_llm_call` and assert the reranker's system prompt was genuinely
invoked during a real `process_goal` run -- required seeding a second real indexed chunk, since
reranking correctly no-ops on a single-candidate result set (Phase 78's own design), caught by
this test on the first run. 89/89 master suite passing, no regressions. Closes the one
remaining item explicitly deferred (not built) in
Phase 81 as a real cost trade-off: `_execute_real_agent_step`'s grounding search
(`intelligence_engine.py:267`, Phase 69) still runs at `rerank`'s default `False`.

## The trade-off, stated plainly

This call runs once per non-tool plan step, for every real `process_goal` run (Phase 69).
Turning on reranking here adds one real LLM call per step on top of the step's own real
`AgentService.execute_agent` call -- roughly doubling real LLM calls (and their latency/cost)
for every agent-driven plan step. That's a real, ongoing cost, not a one-time toggle -- Phase
81 deliberately left it off pending an explicit decision rather than silently adding it.
Enabling it now, since it was flagged rather than built and the user asked to close it out.

## Design

- `ContextEngineService(self.db).search_context(...)` in `_execute_real_agent_step` gains
  `rerank=True`, identical to Phase 81's `POST /context/search` change -- same real mechanism,
  same safe fallback to the un-reranked vector order on any failure (Phase 78).
- No other change -- `top_k=3` is small, but Phase 78's design reranks whenever there's more
  than one real candidate, not only on overflow past `top_k`, so reordering this exact 3-item
  set still has real value.

## Files expected to change

- `backend/app/services/intelligence_engine.py` -- `rerank=True` on the grounding search call.
- `backend/tests/test_real_agent_step_execution.py` -- extend to assert reranking is genuinely
  triggered during real agent step execution, same verification precedent as Phases 78/81.

## Test plan

- A real `process_goal` run with a real db session triggers a real reranking call during
  grounding-context assembly (mocked `BaseAgent._llm_call`, asserted called at least once for
  the search-reranking prompt specifically, distinguishable from the agent's own execution
  call by prompt content).
- Existing Phase 69 assertions (real `AgentExecution` rows, no-db fallback preserved) remain
  green, unmodified.
- Master suite stays green (89/89, unchanged count).
