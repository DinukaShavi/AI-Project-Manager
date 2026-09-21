# Phase 64 Plan: Calendar Attendee Resolution

**Status:** Implemented and verified. 4/4 feature checks passing standalone; 78/78 master
regression suite passing (one unrelated pre-existing timing-sensitive rate-limiter flake seen
in an interim run, confirmed to pass standalone and on a clean full rerun — not caused by this
phase). Roadmap Step 6 (audit Phase I's remaining half).

## What's already there, re-verified

`POST /integrations/calendar/meetings` (Phase 56) already creates real Google Calendar
events, but `attendee_emails: Optional[List[str]]` is raw, unvalidated, free-typed text — the
frontend's Schedule-a-Meeting form (`frontend/app/calendar/page.tsx:112-128`) is a plain
comma-separated text input (`meetingAttendees.split(",")`). A PM has to know and correctly
type every attendee's exact email by hand; a typo silently invites nobody in particular and
no error surfaces.

The org's real member list already exists and is real (Phase 52):
`GET /organizations/members` (`app/api/v1/organizations.py:248-272`) returns tenant-scoped
`{id, email, full_name, roles}`. It's `OrgAdmin`-gated (`_require_org_admin`), which is correct
for its actual purpose (the Settings Console's role table) but too restrictive to reuse
as-is for "pick a teammate as a meeting attendee" — any org member should be able to see their
own org's directory to invite a colleague, not just admins. Per the standing rule against
loosening existing RBAC, this calls for a new, narrower, self-service endpoint rather than
relaxing `/organizations/members`'s admin gate.

## Design

- **New endpoint**: `GET /organizations/members/directory` — any authenticated org member
  (no admin gate), tenant-scoped from the JWT, returns only `{id, email, full_name}` per
  member (no `roles` — unnecessary for attendee-picking, minimal exposure). Backed by the
  same `OrganizationService.list_members` already used by the admin endpoint — no new query
  logic, just a differently-gated, differently-shaped response.
- **`CreateCalendarEventRequest`** gains `attendee_user_ids: Optional[List[UUID]] = None`,
  kept alongside the existing `attendee_emails` (still useful for inviting someone outside the
  org, e.g. a client or vendor) rather than replacing it.
- **`IntegrationService.create_calendar_event`**: resolves `attendee_user_ids` to real `User`
  rows scoped to `organization_id` via a single query; raises `LookupError` (404) if any id
  doesn't belong to this org (decisive rejection, matching the established "repository must be
  linked" / "project must have a jira key" pattern, rather than silently dropping bad ids).
  Resolved emails are merged with `attendee_emails`, deduplicated, and that combined real list
  is what's sent to the real Google Calendar API call and stored on the `Meeting` row — no
  schema change needed, `Meeting.attendees` stays a plain email-string list.
- **Frontend**: the free-text attendee box becomes a multi-select populated from
  `GET /organizations/members/directory`, showing `full_name <email>`; still allows typing an
  extra raw external email alongside picked teammates.

## Files expected to change

- `backend/app/api/v1/organizations.py` — new `GET /members/directory` endpoint.
- `backend/app/api/v1/integrations.py` — `CreateCalendarEventRequest` gains
  `attendee_user_ids`.
- `backend/app/services/integration.py` — `create_calendar_event` resolves and merges
  attendee user ids.
- `backend/tests/test_calendar_attendee_resolution.py` (new).
- `backend/tests/run_all_tests.py` — register Phase 64.
- `frontend/api/organization.api.ts`, `frontend/api/calendar.api.ts`,
  `frontend/types/organization.ts`, `frontend/types/calendar.ts`,
  `frontend/app/calendar/page.tsx` — directory fetch + multi-select attendee picker.

## Test plan

- Real event created with `attendee_user_ids` resolved to real member emails, merged with a
  raw `attendee_emails` entry, deduped.
- An `attendee_user_ids` entry belonging to a different org → `404`, no event created.
- `GET /members/directory` accessible to a non-admin org member (proving it's genuinely
  self-service, not accidentally still admin-gated) and tenant-scoped (Org B never sees Org
  A's members).
- Master suite stays green (78/78 expected).
