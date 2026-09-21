# Phase 66 Plan: Real-Time Activity Push

**Status:** Implemented and verified. 3/3 feature checks passing standalone; 80/80 master
regression suite passing. Roadmap Step 9 (audit Phase J).

## What's already there, re-verified

The WebSocket infrastructure is real and working: `ConnectionManager`
(`app/realtime/connection_manager.py`) tracks org-scoped connections; `IntegrationService.
_broadcast_integration_status` already broadcasts real OAuth connection-status changes over it
(`implementation_roadmap.md` Milestone 6). The frontend already has a working consumer pattern
(`hooks/useIntegrationStatusSocket.ts`) — auto-reconnecting, JWT-authenticated, org-scoped.

What's missing is exactly the audit's finding: broadcasts only ever cover OAuth connection
status. Real GitHub/Jira/Slack activity (Phases 58/59's `ContextIngestionService`, which
already processes every real webhook/backup-sync event into Context Chunks and Knowledge
Graph edges) never pushes anything live — a PM has to manually refresh to see new PRs, issues,
or messages.

## Design

- **`ContextIngestionService.handle_event`** (`app/services/context_ingestion.py`) is the
  single real choke point every real GitHub/Jira/Slack event already passes through — the
  natural place to add a broadcast, reusing infrastructure rather than building a second event
  system. After a chunk is successfully indexed, broadcast:
  ```json
  {"event": "activity_update", "payload": {
      "source_type": "github_pr", "title": "...", "project_id": "...",
      "url": "...", "provider": "github", "timestamp": "..."
  }}
  ```
  to the event's real `organization_id` via the existing `ConnectionManager`. Skipped (no
  broadcast) when indexing failed or no real `project_id` resolved, since an unscoped event
  isn't useful to show against project-scoped UI.
- **Extractors gain an explicit `title`** in their metadata dicts (`_extract_github`,
  `_extract_jira`, `_extract_slack`) — currently only `repo`/`number`/`action` etc.; the
  broadcast (and any future consumer) needs a short human-readable label, not the full
  indexed body text.
- **Frontend**: new `useActivityFeedSocket()` hook, structurally identical to
  `useIntegrationStatusSocket` (same reconnect/JWT pattern), accumulating the last 50
  `activity_update` events (newest first) instead of a status map.
- **New "Live Activity" panel** on the main dashboard (`app/page.tsx`, under the existing
  "overview" tab) — a compact real-time list (provider icon, title, relative time, link to the
  provider), proving the exact gap the audit named: new activity appears without a manual
  refresh.

## Explicitly out of scope for this turn

- Persisting the activity feed server-side (e.g. a `GET /activity/recent` REST fallback for a
  client that missed a broadcast while disconnected) — this turn is the live-push mechanism
  itself; a durable feed/notification-center is a larger, separate feature.
- Calendar activity (meeting created/updated) is not routed through
  `ContextIngestionService` at all (Calendar is polling-driven, not event-bus-driven, per
  existing architecture docs) — out of scope here, could be a small follow-up broadcasting
  from `create_calendar_event`/`sync_calendar_events` directly if wanted later.

## Files expected to change

- `backend/app/services/context_ingestion.py` — title in extractor metadata; broadcast call
  in `handle_event`.
- `backend/tests/test_realtime_activity_push.py` (new) — asserts a real event flowing through
  `handle_event` produces a real broadcast call with the correct organization_id/payload
  (mocking `ConnectionManager.broadcast_to_organization`, the same boundary
  `test_integration_realtime_status_flow` already mocks for the existing OAuth-status
  broadcast).
- `backend/tests/run_all_tests.py` — register Phase 66.
- `frontend/hooks/useActivityFeedSocket.ts` (new), `frontend/types/activityFeed.ts` (new),
  `frontend/app/page.tsx` — Live Activity panel.

## Test plan

- A real GitHub/Jira/Slack event processed by `handle_event` triggers exactly one broadcast
  call, correct organization_id, correct payload shape (title, source_type, project_id, url).
- An event that fails to index, or resolves no project, produces no broadcast.
- Cross-tenant: broadcasting to organization_id A never reaches a connection registered under
  organization_id B (verified against `ConnectionManager`'s existing per-org isolation, not
  re-implemented).
- Master suite stays green (80/80 expected).
