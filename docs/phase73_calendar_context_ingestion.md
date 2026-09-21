# Phase 73 Plan: Calendar Joins the Centralized Context Pipeline

**Status:** Implemented and verified. 4/4 feature checks passing standalone (real synced-
meeting indexing, real ATTENDS graph edges for both attendees, real ContextSnapshot
regeneration, real created-meeting indexing via the write path); 85/85 master regression
suite passing. Closes the one integration-shaped gap
left in "Centralized Context Readiness" (readiness-audit §4 / P0 in the latest revision):
Calendar was the only one of the four real integrations that never flowed through
`ContextIngestionService`, so calendar activity was real and visible in `GET
/calendar/meetings`, but never reached the knowledge graph, `ContextSnapshot`, or the real-time
activity feed the other three integrations have shared since Phases 58/59/66/68.

## What's already there, re-verified

`ContextIngestionService.handle_event` (Phase 58) is the single choke point every real
GitHub/Jira/Slack event passes through: index as a `ContextChunk`, upsert knowledge-graph
edges (Phase 59), broadcast a live `activity_update` (Phase 66), regenerate a throttled
`ContextSnapshot` (Phase 68). All four of those consumers are provider-agnostic already --
`handle_event` just dispatches on `payload["provider"]` to one of three `_extract_*` methods
that turn a normalized payload into `(source_type, external_id, text, metadata, resolve)`.
Adding a fourth provider is exactly the "reuse existing architecture" pattern this whole
pipeline was built around, not new plumbing.

The other three providers all reach `handle_event` via real webhook -> `Event` row -> Outbox
-> Redis stream -> `BackgroundEventWorker`, because that's how their real data actually enters
the system. Calendar is different and was investigated on its own terms rather than forced
into that same shape: `sync_calendar_events` and `create_calendar_event`
(`backend/app/services/integration.py:1265-1469`) are Calendar's *only* real data-ingestion
paths (Calendar is polling-driven, documented in `detailed_component_architecture.md`'s Sync
Frequency Matrix -- the existing Google webhook receiver only ever stores a change signal,
never real event data), and both already know the real `project_id` at the point a `Meeting`
row is written -- Calendar events are project-scoped from creation, never inferred from a
repo/project-key/channel the way GitHub/Jira/Slack need `resolve()` callbacks for.

## Design

- **`ContextIngestionService._extract_calendar(payload)`** (new) -- same shape contract as
  `_extract_github`/`_extract_jira`/`_extract_slack`, but with `resolve=None` always: no
  project-resolution callback needed, since `project_id` is already real and present in the
  event by the time either Calendar write path calls `handle_event`. Indexes
  `f"{title}\n\n{description}"` (plus an `Attendees: ...` line when present) as `source_type
  "calendar_meeting"`.
- **`_extract_graph_edges`** gained a `provider == "calendar"` branch: one `ATTENDS` edge per
  real attendee email (`urn:calendar:meeting:{id}` -> `urn:user:email:{email}`) -- the same
  best-effort, empty-list-is-fine convention every other provider branch already follows.
- **`handle_event`** gained `elif provider == "calendar": extracted = self._extract_calendar(payload)`.
- **No new Event Bus stream.** Inventing a `calendar_stream` + a fake `Event` row + Outbox
  detour for a source that has no webhook to originate one from would be new plumbing solving
  a problem Calendar doesn't have. Instead, `sync_calendar_events` and `create_calendar_event`
  call `ContextIngestionService().handle_event(...)` **directly**, right where each real
  `Meeting` row is written -- for Calendar, the poll (or the real create-event call) *is* the
  ingestion event. Both calls are best-effort (`try/except` + `logger.warning`, matching the
  same discipline `handle_event`'s own internal broadcast/graph/snapshot steps already use) so
  an ingestion failure never breaks a successful sync or a successful meeting creation.
- `sync_calendar_events` calls `handle_event` once per synced event, after its own
  `self.session.commit()` -- `handle_event` opens its own independent `SessionLocal()`
  session and never re-reads the `Meeting` row (everything it needs is passed directly in the
  payload), so there's no session-ordering dependency between the two.
- Repeated re-indexing of an unchanged meeting on every 15-minute poll is accepted, not
  specially avoided -- `ContextEngineService.index_document`'s existing delete-then-reindex
  idempotency (Phase 58) already makes this safe, and it's the same behavior the Jira
  backup-sync poller's `_extract_jira` "backup_sync" branch already has for unchanged issues.

## Explicitly out of scope for this turn

- Any change to the Google Calendar webhook receiver (still change-signal-only, unchanged --
  not part of this gap).
- Resolving attendee emails to real AI-TPM `User` rows for the `ATTENDS` edge (Phase 64's
  member directory could do this) -- the edge uses the real email URN directly; upgrading it
  to a resolved user URN is a natural but separate follow-up.

## Files changed

- `backend/app/services/context_ingestion.py` -- `_extract_calendar`, calendar branch in
  `_extract_graph_edges` and `handle_event`.
- `backend/app/services/integration.py` -- `sync_calendar_events` and `create_calendar_event`
  both call `ContextIngestionService().handle_event(...)` for each real meeting written.
- `backend/tests/test_calendar_context_ingestion.py` (new).
- `backend/tests/run_all_tests.py` -- register Phase 73.

## Test plan

- A real `sync_calendar_events` call with real synced events results in real `ContextChunk`s
  indexed under `source_type="calendar_meeting"`, a real `ATTENDS` graph edge per attendee, and
  a stale project's `ContextSnapshot` regenerated -- same pipeline, same assertions Phase 58/59
  /68's own tests already make for GitHub, applied to Calendar.
- A real `create_calendar_event` call produces the same real ingestion side effects.
- An ingestion failure (simulated) does not raise out of either `sync_calendar_events` or
  `create_calendar_event` -- the real Meeting write still succeeds.
- Cross-tenant isolation: unaffected by this phase (no new endpoint), but the indexed chunk's
  `organization_id` is verified correct.
- Master suite stays green (85/85 expected).
