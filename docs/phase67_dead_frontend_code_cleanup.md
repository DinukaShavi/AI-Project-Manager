# Phase 67 Plan: Dead Frontend API Client Cleanup

**Status:** Implemented and verified. `npx tsc --noEmit` clean; 80/80 backend master suite
passing (same count — pure deletion, no new suite). One additional orphaned component
(`components/github/RepositoryList.tsx`, rendering the now-removed mock `GitHubRepository`
shape, zero importers anywhere) found and removed during verification, beyond the originally
scoped list. Roadmap Step 10 (audit's §6 dead-code list, audit Phase L).

## Scope

A dedicated audit agent re-verified the original audit's ~15-item dead-code list against the
current codebase (nothing has been wired up since) and traced one hop further where a
function was only called by an equally-unused wrapper. Confirmed dead, with zero call sites
outside their own definitions:

- `agentApi.getPersonas`, `getAgentState`, `transitionAgentState`
- `analyticsApi.getBurndownTrajectory`, `getPredictiveCompletionForecast`
- `authApi.register`, `updateUserProfile`
- `contextApi.indexDocument`, `searchMemory`
- `costsApi.getCostAlerts`, `recordUsage`
- `graphApi.linkEntities`, `inferEdges`, `decaySweep`
- `modelRouterApi.routeTask`
- `observabilityApi.injectSpan`
- `projectApi.createWorkspace`, `getProjectById`
- `rateLimiterApi.getBucketStatus`
- `securityApi.maskPII`, `sanitizeInput`
- `taskApi.updateTaskDetails`, `getTaskById`
- `workflowApi.getTemplates`, `getExecutionStatus`
- The entire file `frontend/api/integrations.api.ts` (legacy, superseded by
  `integrationOAuth.api.ts`/`integrationStatus.api.ts`) — its export is never imported.
- `frontend/lib/api.ts` — a backward-compat façade; only 2 of its 15 exports
  (`executeAgentPersona`, `createProjectTask`) have any real caller
  (`AgentActionsConsole.tsx`). The other 13 wrap several of the items above and are
  themselves uncalled.

Plus the three confirmed dead this session, whose **backend mock routes also get retired**
(unlike the rest of this list, these have a real, already-shipped replacement — the same
precedent as Phase 65 deleting `/google/meetings`/`/google/availability` outright):
- `githubApi.getRepositories`/`useGithubRepositories` — real replacement:
  `discover-repositories`/`linked-repositories` (Phase 54). Backend mock `GET
  /github/repositories` deleted.
- `slackApi.getChannels`/`useSlackChannels` — real replacement: `discover-channels`/
  `mapped-channels` (Phase 57). Backend mock `GET /slack/channels` deleted.
- `calendarApi.getEvents`/`useCalendarEvents` — real replacement: `GET /calendar/meetings`
  (Phase 50/56). Backend mock `GET /google/events` deleted.

## What does NOT get touched

The ~21-item list's **backend endpoints are left exactly as they are** — unlike the three
above, most of these correspond to real, working, tested backend capabilities
(agent personas, cost tracking, rate limiting, PII masking, etc.) that simply have no frontend
UI yet, not fake/mock data. Removing the frontend wrapper doesn't remove the capability; it's
trivial to re-add a thin API client method whenever a future turn builds real UI for one of
these. This turn is frontend dead-code removal only.

`frontend/lib/api.ts`'s two live exports (`executeAgentPersona`, `createProjectTask`) and
their underlying real API methods are untouched.

## Verification approach

This is pure deletion of unreferenced code — nothing to unit-test. Verification is:
`tsc --noEmit` passes (no broken imports from the deletions), and the backend master suite
stays green (proves no still-tested backend route was accidentally touched, since none of the
~21-item backend endpoints are being changed — only the three retired mocks, covered by
updating/removing their now-obsolete assertions if any test references them).

## Files expected to change

- Deleted: `frontend/api/integrations.api.ts`.
- Trimmed: `frontend/api/{agent,analytics,auth,context,costs,graph,modelRouter,observability,
  project,rateLimiter,security,task,workflow}.api.ts` (remove only the confirmed-dead methods
  — a file whose every method is dead gets removed entirely, matching integrations.api.ts's
  treatment).
- Trimmed: `frontend/lib/api.ts` (remove the 13 dead wrappers, keep the 2 live ones).
- Trimmed: `frontend/api/index.ts` (drop the `integrationsApi` re-export).
- `frontend/api/github.api.ts`, `frontend/hooks/useGithub.ts`, `frontend/types/github.ts` —
  remove `getRepositories`/`useGithubRepositories`/`GitHubRepository`/
  `GitHubRepositoriesResponse`.
- `frontend/api/slack.api.ts`, `frontend/hooks/useSlack.ts`, `frontend/types/slack.ts` —
  remove `getChannels`/`useSlackChannels`/`SlackChannel`/its response type.
- `frontend/api/calendar.api.ts`, `frontend/hooks/useCalendar.ts`, `frontend/types/calendar.ts`
  — remove `getEvents`/`useCalendarEvents`/`CalendarEvent`.
- `backend/app/api/v1/integrations.py` — delete the three retired mock routes
  (`/github/repositories`, `/slack/channels`, `/google/events`).
- `backend/tests/run_all_tests.py` — no suite count change (nothing new to register); confirm
  no existing test asserted against the three deleted mock routes.

## Test plan

- `npx tsc --noEmit` passes with zero errors after every deletion.
- Backend master suite stays green (80/80 — same count, since this turn adds no new suite).
