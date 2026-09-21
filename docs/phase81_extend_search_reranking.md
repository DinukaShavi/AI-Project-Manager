# Phase 81 Plan: Extend Real Search Reranking to the Human-Facing Search Endpoint

**Status:** Implemented and verified. Extended `test_context_engine.py`'s existing HTTP search
test to mock the real LLM call and assert it was genuinely triggered (1/1 check, matching
Phase 78's own verification precedent); 89/89 master suite passing, unchanged suite count.
Second item of the second grounded plan (Monte Carlo real-data
inputs → ~~GitHub/Jira `ASSIGNED_TO` edge resolution~~ (already done, Phase 75 -- caught before
implementing, see below) → **extend reranking**).

## Correction before starting

The originally-proposed item 2 ("resolve GitHub/Jira `ASSIGNED_TO` edges via
`ExternalIdentity`") turned out to already be shipped -- Phase 75 did exactly this
(`ContextIngestionService._resolve_user_urn`, both the GitHub and Jira branches of
`_extract_graph_edges`). Verified live in the current code before writing anything, caught the
duplication, and skipped straight to item 3 rather than silently redoing already-real work.

## What's already there, re-verified

Every real caller of `ContextEngineService.search_context` in the application, found by a
direct grep (not assumption):

- `app/tools/context_tools.py:46` (`ContextSearchTool`) -- already `rerank=True` since Phase
  78.
- `app/api/v1/context.py:73` (`POST /context/search`) -- the real, authenticated, human-facing
  search endpoint (the one a PM's own search bar calls) -- still at the `rerank=False` default.
- `app/services/intelligence_engine.py:267` (`_execute_real_agent_step`'s grounding search,
  Phase 69) -- also still at the default.

Phase 78's own doc named "Phase 68's snapshot generation" as a second candidate; re-checked
directly and it's wrong -- `ContextSnapshotService._gather_recent_chunks`
(`context_snapshot.py:51-58`) is a plain "most recent N chunks" `ORDER BY created_at DESC`
query with no search query or relevance concept at all, not a `search_context` call. Reranking
doesn't apply there; corrected rather than carried forward.

## Design

- **`POST /context/search` gets `rerank=True`.** This is the one clear, low-risk extension:
  a human directly reads these results, calls are infrequent (a person typing a query) rather
  than a hot loop, and the added LLM-call latency is well justified by the quality gain --
  exactly the profile Phase 78 built `rerank` for.
- **`_execute_real_agent_step`'s grounding search is deliberately left at the default,** not
  turned on. This call runs on *every* real agent step execution (Phase 69) -- turning on
  reranking there means doubling real LLM calls (and latency/cost) for every single plan step,
  a real product/cost trade-off that wasn't part of what was agreed, not a free extension.
  Documented here explicitly rather than silently done or silently skipped.

## Files expected to change

- `backend/app/api/v1/context.py` -- `rerank=True` on the `search_context` call.
- `backend/tests/test_context_engine.py` -- extend the existing HTTP search test to assert
  reranking is exercised (matches Phase 78's own precedent of monkeypatching
  `BaseAgent._llm_call` to verify a real call was made).

## Test plan

- `POST /context/search` triggers a real reranking call (mocked `BaseAgent._llm_call`,
  asserted called) and returns results in the mocked reranked order.
- Existing `test_context_engine.py` assertions (indexing, unreranked-shape checks elsewhere)
  remain green.
- Master suite stays green (89/89, unchanged count -- extends an existing suite, no new file).
