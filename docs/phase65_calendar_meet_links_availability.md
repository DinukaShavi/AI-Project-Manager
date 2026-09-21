# Phase 65 Plan: Real Google Meet Links & Team Availability

**Status:** Implemented and verified. 5/5 feature checks passing standalone; 79/79 master
regression suite passing. Roadmap Step 5 (the three leftover Google mock endpoints), decided
per-endpoint per the roadmap's own instruction.

## Investigation: three endpoints, three different outcomes

- **`GET /google/events`** — confirmed dead code. Its hook (`useCalendarEvents`) isn't
  imported anywhere in `frontend/app/calendar/page.tsx`; the "Events" tab already renders the
  real `syncedMeetings` state (Phase 50/56). Same shape as GitHub's dead
  `/github/repositories` and Slack's dead `/slack/channels` — left alone, Phase L candidate.
- **`GET /google/meetings`** (Google Meet links) — still mock, still live: the "Meetings" tab
  calls it via `useCalendarMeetings`. Real data is achievable: Google Calendar's `events`
  resource supports `conferenceDataVersion=1` at creation time to auto-generate a real Meet
  link (`conferenceData.entryPoints[].uri`), and already-synced events may carry one too if a
  PM created them with a Meet attached via Google's own UI — `sync_calendar_events` currently
  discards this field entirely.
- **`GET /google/availability`** — still mock, still live: the "Availability" tab calls it via
  `useCalendarAvailability`. Real data is achievable via Google Calendar's `freeBusy.query`
  endpoint, using the org's real member emails (Phase 64's new directory) and the org's real
  Calendar OAuth token.

Both live mock endpoints are closed out this turn — no deferrals needed here, unlike the
Jira/Slack turns.

## Design

### Meet links
- **Migration**: add `Meeting.meet_link` (`String`, nullable).
- **`GoogleCalendarConnector.create_event`**: add `conferenceDataVersion=1` query param plus
  `conferenceData: {createRequest: {requestId: <uuid4>, conferenceSolutionKey: {type:
  "hangoutsMeet"}}}` in the request body; extract `conferenceData.entryPoints[].uri` (falling
  back to the top-level `hangoutLink` field Google also sometimes sets) from the response.
- **`GoogleCalendarConnector.list_events`**'s callers (`sync_calendar_events`) already receive
  full event objects — extract the same field there too, so pre-existing real events picked up
  by a sync (not created through AI-TPM) also get their real Meet link stored.
- **`create_calendar_event` / `sync_calendar_events`**: store the extracted `meet_link` on the
  `Meeting` row (create and update paths both).
- **`GET /calendar/meetings`**: add `meet_link` to the existing real response shape.
- **Mock `GET /google/meetings` is deleted outright**, not deprecated-in-place (matches the
  webhook-route precedent from Phase 60 — a working real replacement exists, no reason to
  leave the fake one reachable). Frontend "Meetings" tab is repointed at the same real
  `syncedMeetings` state the "Events" tab already loads (no new API call), rendered as
  meeting-focused cards with a real "Join Meet" button when `meet_link` is present.

### Team availability
- **`GoogleCalendarConnector.query_freebusy(emails, time_min, time_max)`** → real
  `POST /freeBusy` call, returns each email's real busy intervals.
- **`IntegrationService.get_team_availability(organization_id, time_min, time_max)`**:
  resolves the org's real Calendar OAuth token and real member list (reusing
  `OrganizationService.list_members`, the same real data source Phase 64 exposed via the
  directory); calls `query_freebusy` for all member emails; computes available slots by
  generating fixed 1-hour candidate slots across **09:00–17:00 UTC** for each day in range and
  keeping, per slot, the list of members with no busy interval overlapping it. This is a fixed,
  documented simplification (not a full timezone-aware scheduling engine) — real computation
  over real data, not fabricated, but intentionally bounded in scope.
- **New endpoint**: `GET /integrations/calendar/availability?start_date=&end_date=` (auth-gated,
  org derived from JWT), replacing the mock `GET /google/availability`, which is deleted
  outright. `400` if Calendar isn't connected.

## Files expected to change

- New Alembic migration: `Meeting.meet_link`.
- `backend/app/models/project.py` — the column.
- `backend/app/integrations/calendar.py` — `query_freebusy`, conference-data request/response
  handling in `create_event`, Meet-link extraction shared by `list_events` callers.
- `backend/app/services/integration.py` — `get_team_availability`; `create_calendar_event` and
  `sync_calendar_events` store `meet_link`.
- `backend/app/api/v1/integrations.py` — new `GET /calendar/availability`; `GET
  /calendar/meetings` gains `meet_link`; `GET /google/meetings` and `GET /google/availability`
  deleted.
- `backend/tests/test_calendar_meet_links_availability.py` (new).
- `backend/tests/run_all_tests.py` — register Phase 65.
- `frontend/api/calendar.api.ts`, `frontend/types/calendar.ts`, `frontend/hooks/useCalendar.ts`
  (drop the now-dead `useCalendarMeetings`/`useCalendarAvailability` mock hooks),
  `frontend/app/calendar/page.tsx` (Meetings tab repointed at real synced data; Availability
  tab wired to the new real endpoint).

## Test plan

- Real event creation requests a Meet link; the response's link is stored and returned via
  `GET /calendar/meetings`.
- A synced (not AI-TPM-created) event carrying a real `hangoutLink` gets it stored too.
- Real availability: a member with a busy interval overlapping a candidate slot is correctly
  excluded from that slot's `participants_available`; a member with no conflict is included.
- Calendar not connected → `400` for both new/changed endpoints.
- Old mock routes (`/google/meetings`, `/google/availability`) are gone (`404`).
- Cross-tenant isolation.
- Master suite stays green (79/79 expected).
