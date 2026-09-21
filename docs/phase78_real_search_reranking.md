# Phase 78 Plan: Real Search Reranking

**Status:** Implemented and verified. 5/5 feature checks passing standalone (default behavior
byte-for-byte unchanged with zero LLM calls, exact reorder verified against a real mocked LLM
response, safe fallback on a failing call, safe filtering of invalid/duplicate indices,
`ContextSearchTool` end-to-end); 88/88 master suite passing. One design refinement made during
implementation: reranking runs whenever there's more than one real candidate, not only when
the pool overflows past `top_k` (the original plan) -- reordering the exact top-`k` set by
relevance is real value on its own. Second of the three-part depth phase (broaden real actions → **real
search reranking** → Calendar push-based real-time), targeting the audit's Memory score (65):
`ContextEngineService.search_context` currently ranks purely by pgvector cosine-distance
ordering, with no reranking pass on top.

## What's already there, re-verified

`ContextRepository.search_context` (`app/repositories/context.py:66-85`) already does a real,
correct vector similarity search -- `ORDER BY <=> LIMIT` pushed down to Postgres/pgvector
(with a Python-side fallback when the extension isn't installed). Nothing wrong with it; a
reranking pass sits *on top* of real vector results, it doesn't replace them. `_llm_call`
infrastructure (Phase 26, reused by Phases 69/71/72/77) is the obvious fit -- same "ask a real
LLM, validate the response, fall back to the already-correct un-reranked order on any failure"
shape every prior depth/NLP phase in this engagement has used.

## Design

- **`ContextEngineService.search_context` gains an opt-in `rerank: bool = False` parameter.**
  Default unchanged (`False`) -- every existing caller (Phase 69's grounding search, Phase
  68's snapshot generation, any other internal use) keeps its current latency/cost profile
  with zero behavior change. Explicit opt-in avoids silently adding an LLM call (latency +
  cost) to call sites that never asked for it.
- **When `rerank=True`:** over-fetches a larger real candidate pool from the same real vector
  search (`min(top_k * 4, 20)` instead of just `top_k`), then reranks via a real LLM call --
  a minimal `_RerankLLM(BaseAgent)` carrier (same pattern as Phase 71's `_PlannerLLM`, Phase
  72's `_SentimentLLM`) asked to return a JSON array of the most relevant candidate indices,
  best-first, down to `top_k`. Reranking runs whenever there's more than one real candidate,
  not only when the pool overflows past `top_k` -- reordering the exact top-`k` set by
  relevance is real value on its own, not just a trim. Falls back to the original
  vector-similarity order -- already real, already correct -- on any failure (unconfigured,
  bad response, invalid indices), same fallback discipline as every prior LLM-backed phase.
- **`ContextSearchTool`** (the concrete tool an AI agent actually calls when reasoning,
  `app/tools/context_tools.py`) is switched to `rerank=True` -- the one call site this phase
  wires it into, since it's the clearest "the AI is searching its memory" moment where result
  quality most directly matters. Other internal callers (Phase 69's grounding assembly, Phase
  68's snapshot generation) are left at the default for now -- real capability now exists for
  them to opt into later without further plumbing, not bundled into this phase's scope.

## Explicitly out of scope for this turn

- Enabling reranking on every `search_context` caller -- deliberately opt-in per the above,
  not a blanket default change.
- A dedicated `SEARCH_RERANKING` `ModelRouter` category -- Phase 72/76's investigation already
  found that category has no real provider wiring (Cohere) and no real caller; this phase
  reuses the already-real `output_reflection` route (Claude/GPT-4o) instead, consistent with
  every other LLM-backed phase in this engagement.

## Files expected to change

- `backend/app/services/context.py` -- `_RerankLLM`, `rerank` parameter, `_rerank` helper.
- `backend/app/tools/context_tools.py` -- `ContextSearchTool` passes `rerank=True`.
- `backend/tests/test_search_reranking.py` (new).
- `backend/tests/run_all_tests.py` -- register Phase 78.

## Test plan

- `rerank=False` (default): `search_context` behavior is byte-for-byte unchanged from before
  this phase -- same result count, same order, no LLM call made.
- `rerank=True` with a real (mocked) LLM response: results are reordered per the mocked
  ranking, not left in vector-similarity order.
- `rerank=True` with an unconfigured/failing LLM: falls back to the exact original
  vector-similarity order -- never crashes, never returns fewer than the un-reranked path
  would have.
- `rerank=True` with a real LLM response naming out-of-range/duplicate indices: those are
  filtered, not allowed to corrupt the result list.
- `ContextSearchTool` end-to-end: real search_context call made with `rerank=True`.
- Master suite stays green (88/88 expected).
