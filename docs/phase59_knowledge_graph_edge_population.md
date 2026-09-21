# Phase 59 Plan: Knowledge Graph Edge Auto-Population

**Status:** Implemented and verified. 7/7 feature checks passing standalone; 73/73 master
regression suite passing. Kept as the design record for this feature per standing process:
one plan `.md` per feature, written before implementation, committed to `docs/`.

## Why this feature, why now

Phase 58 (`app/services/context_ingestion.py`) wired the previously-unused Event Bus
`subscribe()` path into a real consumer that indexes GitHub/Jira/Slack webhook and
backup-sync activity into the Context Engine's vector store (`ContextChunk`/`ContextEmbedding`).
That closed one half of the P3 "centralized context" gap identified in the product-readiness
audit. The other half — the Knowledge Graph (`KnowledgeGraphEdge`, queried by
`GET /context/projects/{id}/graph` and `ProjectKnowledgeGraph`) — is still only ever written
to by hand (see `test_project_knowledge_graph.py`, which inserts an edge directly). No real
GitHub/Jira activity produces graph edges automatically. This plan closes that second half,
using the exact same already-consumed event stream Phase 58 subscribed to, so no new
subscription plumbing is needed.

## Scope for this turn

Extend the existing Phase 58 consumer pipeline to *also* derive graph edges from the same
webhook/backup-sync payloads it already parses for text content. Three relation types,
chosen because they're derivable directly from fields already present on the normalized
payloads (no new API calls, no new scopes):

1. **`RESOLVES`** — a GitHub PR body containing `resolves #N` / `closes #N` / `fixes #N`
   (case-insensitive, GitHub's own linking-keyword convention) produces an edge
   `urn:github:pr:{repo}#{pr_number}` → `urn:github:issue:{repo}#{N}`.
2. **`ASSIGNED_TO`** (GitHub) — a GitHub issue/PR webhook payload carrying a non-null
   `assignee` produces an edge `urn:github:{issue|pr}:{repo}#{number}` →
   `urn:github:user:{login}`.
3. **`ASSIGNED_TO`** (Jira) — a Jira issue payload (webhook or backup-sync) carrying a
   non-null `fields.assignee` produces an edge `urn:jira:issue:{key}` →
   `urn:jira:user:{accountId}`.

Explicitly **out of scope** for this turn (candidates for later, separate turns):
- Slack message → project/channel edges (`DISCUSSED_IN`) — needs a decision on whether a
  per-message graph node is even useful signal vs. noise; deferred until there's a concrete
  consumer (e.g. root-cause traversal) that would use it.
- `BLOCKS` / `DEPENDS_ON` edges — Jira issue-link webhooks (`issuelink_created`) carry this
  but weren't inspected yet; needs its own payload-shape audit first.
- `ContextSnapshot` population (point-in-time project-state summaries with an LLM-generated
  embedding) — this needs a real LLM call to summarize state, which is P4 ("real AI") territory,
  not a P3 ingestion concern. Deliberately not bundled in here.

## Design

- New method on `ContextIngestionService` (same class Phase 58 already runs per event):
  `_extract_graph_edges(provider, payload) -> List[Tuple[urn, urn, relation]]`, called
  alongside the existing `_extract_github`/`_extract_jira` text extraction in `handle_event`,
  from the *same* already-parsed `raw_payload` — no duplicate parsing.
- Edges are written via `KnowledgeGraphEdge` rows directly (not through
  `ProjectKnowledgeGraph.save_to_db`, which is designed around an in-memory graph built for a
  single project's read path, not incremental single-edge upserts). A small
  `GraphRepository.upsert_edge(organization_id, project_id, source_urn, target_urn,
  relation_type)` is added — upsert (not insert-always) so redelivered events don't create
  duplicate edges; matched on `(organization_id, project_id, source_urn, target_urn,
  relation_type)`.
- `project_id` reuses the exact same resolution already computed in `handle_event` for the
  text-indexing path (GitHub repo → linked project, Jira project key → project) — no new
  resolution logic.
- Skip (no edge written) when `project_id` can't be resolved — an edge with no project
  scope isn't queryable by `GET /context/projects/{id}/graph` anyway, and
  `KnowledgeGraphEdge.project_id` is `nullable=False`.

## Files expected to change

- `backend/app/services/context_ingestion.py` — add `_extract_graph_edges`, call it from
  `handle_event` after project_id resolution, alongside the existing chunk-indexing call.
- `backend/app/models/graph.py` — no schema change expected (existing columns cover this).
- New: a small repository method for upsert (`backend/app/repositories/graph.py`, or added to
  an existing repository if one already fits — to be confirmed while reading current code).
- `backend/tests/test_context_ingestion.py` or a new `test_knowledge_graph_ingestion.py` —
  new checks: PR-resolves-issue edge created, GitHub assignee edge created, Jira assignee
  edge created, redelivery upserts instead of duplicating, no-project-resolved skips cleanly,
  and one cross-tenant check (an edge never gets written under the wrong org).
- `backend/tests/run_all_tests.py` — register the new suite (Phase 59).

## Test plan

Direct `handle_event` calls with realistic payloads (same pattern as Phase 58), plus reading
edges back via `GET /context/projects/{id}/graph` to prove the existing read path surfaces
them with zero changes to that endpoint. Master suite must stay green (73/73 expected).

## Open questions (none blocking)

No architecture decision needed to start — this reuses Phase 58's consumer, existing models,
and existing project-resolution logic end to end. Flagging here for visibility rather than as
a blocker: the `BLOCKS`/`DEPENDS_ON` Jira issue-link scope noted above under "out of scope" is
the natural Phase 60 candidate once its payload shape is audited.
