# Phase 68 Plan: ContextSnapshot Population

**Status:** Implemented and verified. 6/6 feature checks passing standalone; 81/81 master
regression suite passing. Roadmap Step 6 (audit Phase G, second half — `ContextSnapshot` was
the only piece of "centralized context" Phases 58/59 didn't already close out).

## Decisions (asked, answered)

1. **Trigger**: event-driven, throttled. Regenerated at the same choke point Phase 66 already
   broadcasts from (`ContextIngestionService.handle_event`, after indexing + graph edges),
   but only if the project's latest snapshot is more than 15 minutes old (or none exists) —
   no new poller, and a project with zero real activity never gets a snapshot at all. A
   secondary on-demand endpoint is added too (see below) so a PM isn't stuck waiting on the
   throttle window if they want a fresh one immediately.
2. **Summary method**: templated from real structured data, embedded with the same embedding
   generator `ContextChunk`s already use (`get_embedding_generator()`) — no LLM completion
   call, no new cost/dependency. Real data, not AI-narrated prose.

## Design

- **Data sources for `state_payload`** (both already real, both direct outputs of Phases
  58/59 — deliberately not reaching into sprint analytics/ProjectTask, a separate subsystem,
  to keep this turn tightly scoped to capping off the ingestion pipeline it's built on):
  - Recent `ContextChunk` rows for the project (last 10, newest first) — source_type, title
    (from `metadata_json["title"]`, added in Phase 66), timestamp.
  - Real Knowledge Graph bottlenecks — `ProjectKnowledgeGraph.load_from_db` +
    `find_bottleneck_clusters()` (both already exist, unused by any snapshot mechanism today).
- **Templated summary text** built from those two real sources (activity counts by source
  type, recent item titles, bottleneck entities with their blocking/blocked-by counts) —
  embedded via `get_embedding_generator().generate_embedding(...)` into
  `ContextSnapshot.summary_embedding`.
- **One row per generation, not an update-in-place** — `ContextSnapshot.snapshot_timestamp`
  is a distinct column, matching a time-series/history intent, not a single mutable "current
  state" row. `get_latest_snapshot` queries `ORDER BY snapshot_timestamp DESC LIMIT 1`.
- **New service**: `ContextSnapshotService` (new file, mirrors `ContextEngineService`'s
  shape) — `generate_snapshot(organization_id, project_id)`, `get_latest_snapshot(...)`.
- **Wiring into `handle_event`**: after the existing broadcast block, check the project's
  latest snapshot age; if stale/missing, call `generate_snapshot`, wrapped in try/except
  (non-fatal, matching this method's established resilience pattern — a snapshot failure must
  never break real event ingestion).
- **Endpoints**: `GET /context/projects/{id}/snapshot` (latest, tenant-scoped, ownership-
  checked — mirrors the existing `_verify_project_ownership` pattern already in
  `context.py`); `POST /context/projects/{id}/snapshot` (on-demand regeneration, same
  ownership check, for the "I want it now" case).
- **Frontend**: a compact "Project Snapshot" panel on the main dashboard (`app/page.tsx`,
  overview tab, alongside the Phase 66 Live Activity panel) showing the latest snapshot's
  timestamp and summary text, with a manual "Regenerate" button hitting the new POST endpoint.

## Explicitly out of scope for this turn

- Feeding `ContextSnapshot` into `ProjectIntelligenceEngine`/`HTNPlanner` (that's Step 7,
  which depends on this turn existing first — separate turn, separate plan doc).
- Sprint analytics / `ProjectTask` data in the snapshot payload — a different real subsystem;
  can be added as a later enrichment once this vertical slice is proven.
- Historical snapshot browsing UI (only the latest is surfaced this turn) — the data model
  supports it (one row per generation), but building a history view is separate scope.

## Files expected to change

- `backend/app/services/context_snapshot.py` (new).
- `backend/app/services/context_ingestion.py` — throttled trigger call in `handle_event`.
- `backend/app/api/v1/context.py` — new GET/POST snapshot endpoints.
- `backend/tests/test_context_snapshot_population.py` (new).
- `backend/tests/run_all_tests.py` — register Phase 68.
- `frontend/api/context.api.ts`, `frontend/types/` (new snapshot types),
  `frontend/app/page.tsx` — Project Snapshot panel.

## Test plan

- Real chunks + real graph bottlenecks produce a real, non-fabricated templated summary,
  embedded and stored as a new `ContextSnapshot` row.
- A second real event within the 15-minute throttle window does not create another snapshot;
  one past the window does.
- `POST /context/projects/{id}/snapshot` bypasses the throttle for an explicit request.
- A project with no real activity has no snapshot (never fabricated).
- Cross-tenant isolation on both endpoints.
- Master suite stays green (81/81 expected).
