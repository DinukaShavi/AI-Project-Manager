# Phase 62 Plan: Real Jira Issues & Sprints (Per-Org OAuth)

**Status:** Implemented and verified. 6/6 feature checks passing standalone; master suite
green in every full run including this phase. Roadmap Step 3 / audit Phase E (partial — see
scope note below).

## What's already there, re-verified

`GET /integrations/jira/projects` was already migrated to real data before this session's
involvement, but via the **global static credential** (`JIRA_BASE_URL`/`JIRA_EMAIL`/
`JIRA_API_TOKEN`, Basic Auth) — explicitly documented in its own docstring as a deliberate,
temporary choice: *"Jira in this system authenticates via a configured API token/email...
not per-tenant OAuth."*

`GET /integrations/jira/issues`, `/sprints`, `/workload`, `/velocity` are still 100% mock
(confirmed unchanged, `backend/app/api/v1/integrations.py`).

Phase 55 already did the harder architectural half of this: `exchange_code_for_token`'s Jira
branch (`backend/app/services/integration.py:422-464`) resolves and stores the org's real
Atlassian Cloud ID into `Integration.external_workspace_id` on OAuth connect. Its own comment
explicitly flags this exact gap: *"Migrating JiraConnector's actual issue/project data calls
onto per-organization OAuth bearer tokens (api.atlassian.com/ex/jira/{cloudId}/...) is
deliberately left for a follow-up phase."* This is that follow-up phase.

## Scope for this turn: Issues + Sprints only, not Workload/Velocity

Investigated all four mock endpoints against what's actually achievable via Jira's public
REST API:

- **Issues** — clean. `GET /rest/api/3/search` (JQL), standard fields (key, summary, status,
  priority, assignee). No ambiguity.
- **Sprints** — clean. Jira Software Agile REST API (`/rest/agile/1.0/board` →
  `/rest/agile/1.0/board/{id}/sprint`), standard fields (name, state, start/end dates).
- **Workload** and **Velocity** both fundamentally depend on **Story Points**, which Jira
  exposes only as a per-instance **custom field** (e.g. `customfield_10016`) with no fixed ID
  — resolvable only best-effort by searching `/rest/api/3/field` for a name match, which isn't
  guaranteed to succeed for every Jira configuration. Velocity additionally has no supported
  public REST endpoint at all — Jira's own Velocity Chart is computed by an internal,
  undocumented Greenhopper API; a real equivalent would have to be reconstructed from
  per-sprint issue snapshots, which is materially more work than Issues/Sprints and shares
  none of their mechanics.

Rather than guess at a custom-field-resolution strategy and a velocity-reconstruction
approach in the same turn as the straightforward Issues/Sprints work, this turn covers Issues
+ Sprints only. Workload/Velocity become Step 3b, scoped separately once story-points
resolution is worked out on its own.

## Design

- **`JiraConnector`** gains a second construction mode: `JiraConnector(access_token=...,
  cloud_id=...)` for real per-org OAuth Bearer-token calls against
  `https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3` (issues) and `.../rest/agile/1.0`
  (sprints) — additive, does not touch the existing `domain`/`api_token`/`user_email` Basic-Auth
  constructor path still used by `/jira/projects`, `transition_issue`, and the backup-sync
  poller (all deliberately left alone, per Phase 55's comment and to avoid touching real,
  working, RBAC/approval-gated tool-execution code for an unrelated turn).
  - `list_project_issues(project_key)` → `GET /search?jql=project={key} ORDER BY updated DESC`
  - `list_boards(project_key)` → `GET /rest/agile/1.0/board?projectKeyOrId={key}`
  - `list_sprints(board_id)` → `GET /rest/agile/1.0/board/{board_id}/sprint`
- **`IntegrationService`**: `get_jira_issues_for_project(organization_id, project_id)` and
  `get_jira_sprints_for_project(organization_id, project_id)` — resolve the org's Jira OAuth
  token + cloud ID via `get_valid_oauth_token`/the stored `Integration.external_workspace_id`
  (raise if not connected); resolve the real Jira project key from `Project.jira_project_key`
  (raise `LookupError` if the project has none set — matches the existing "project not
  configured for this provider" shape used elsewhere); for sprints, resolve the project's
  first accessible board (mirrors the established "first accessible site/workspace" pattern
  from Phase 55's own site resolution) and list its sprints.
- **Endpoints**: `GET /integrations/jira/issues?project_id=X`, `GET
  /integrations/jira/sprints?project_id=X` — replace the free-text `project_key` query param
  (which defaulted to a magic `"TPM"` string) with `project_id`, matching Phase 61's GitHub
  pattern: auth-gated, tenant-scoped ownership check, org derived from JWT. `400` if Jira isn't
  connected for the org; `404` if the project has no `jira_project_key` configured or doesn't
  belong to a real Jira project the token can see.
- **Types**: `JiraIssue.story_points` and `JiraSprint.completed_story_points`/
  `total_story_points` become `number | null` — best-effort resolved via `/rest/api/3/field`
  name-matching ("Story Points" / "Story point estimate"), `null` (not `0`) when the field
  can't be confidently resolved. Frontend renders `—` for `null` rather than a fabricated `0`.

## Files expected to change

- `backend/app/integrations/jira.py` — Bearer-token construction mode, three new methods.
- `backend/app/services/integration.py` — two new service methods, story-points field
  resolution helper.
- `backend/app/api/v1/integrations.py` — rewrite `/jira/issues` and `/jira/sprints`.
- `backend/tests/test_jira_real_issues_sprints.py` (new).
- `backend/tests/run_all_tests.py` — register Phase 62.
- `frontend/api/jira.api.ts`, `frontend/hooks/useJira.ts`, `frontend/app/jira/page.tsx`,
  `frontend/types/jira.ts` — project-scoped real data, `story_points: number | null`.

## Test plan

- Real issues returned for a project with `jira_project_key` set and Jira connected.
- Real sprints returned, story points resolved when the field lookup succeeds, `null` when it
  doesn't (both cases tested explicitly, not just the happy path).
- Jira not connected → `400`.
- Project with no `jira_project_key` → `404`.
- Cross-tenant isolation (Org B can't read Org A's project's real Jira data).
- Master suite stays green (76/76 expected).
