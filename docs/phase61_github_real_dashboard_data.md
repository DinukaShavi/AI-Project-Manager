# Phase 61 Plan: Replace GitHub Mock Reads with Real Data

**Status:** Implemented and verified. 7/7 feature checks passing standalone; 75/75 master
regression suite passing (one transient full-suite hang during verification did not reproduce
on rerun — bisected to confirm Phases 59/60/61 individually and in sequence are unaffected).
Roadmap Step 2 / audit Phase D.

## Scope

Replace the three still-hardcoded GitHub dashboard endpoints with real, authenticated,
tenant-scoped GitHub API data:

- `GET /integrations/github/pull-requests`
- `GET /integrations/github/commits`
- `GET /integrations/github/issues`

Confirmed still 100% mock (`backend/app/api/v1/integrations.py`): no auth dependency, fixed
sample JSON, `organization_id` as an unverified query param. The frontend already knows this —
`frontend/app/github/page.tsx:43-48` has a comment stating these three tabs were deliberately
left on the mock endpoints as "a separate, larger piece of work."

Also confirmed dead (not a mock-data problem, just unused code, left alone this turn): the
separate `GET /integrations/github/repositories` mock endpoint and its `useGithubRepositories`
hook are never called from any page — the "repos" tab already uses the real linked-repositories
list from Phase 54. Not touched here; candidate for Phase L (dead code cleanup) instead of
being folded into this real-data turn.

## Design

- **`GitHubConnector`** (`backend/app/integrations/github.py`) — add three real API calls
  alongside the existing `list_repositories`/`get_pull_request`/`create_issue`:
  - `list_pull_requests(repo, state="all")` → `GET /repos/{repo}/pulls?state=all&sort=updated&direction=desc&per_page=30`
  - `list_commits(repo)` → `GET /repos/{repo}/commits?per_page=30` (defaults to the repo's default branch)
  - `list_issues(repo, state="all")` → `GET /repos/{repo}/issues?state=all&per_page=30`, then
    filters out entries carrying a `pull_request` key — GitHub's issues endpoint includes PRs,
    and this product surface already has a separate PR tab.
- **`IntegrationService`** — three new methods (`get_pull_requests_for_org`,
  `get_commits_for_org`, `get_issues_for_org`), each: resolve the org's real GitHub OAuth token
  via `get_valid_oauth_token` (raise if not connected); resolve which real repos to query —
  scoped to one `project_id`'s linked `Repository` rows, optionally narrowed further to one
  `repository` full_name (verified it's actually linked to that project/org first); call the
  connector once per repo and concatenate; map each provider's raw fields onto the existing
  response contract (`id`/`number`/`title`/`state`/`author`/`repository`/`html_url`/
  `created_at`/...) so the frontend types (`GitHubPullRequest`/`GitHubCommit`/`GitHubIssue`)
  don't need to change shape, only their real values. No linked repos yet → empty list, not
  an error (matches the honest-empty-state convention from Phases 53–59).
- **Endpoints** — require `current_user` (org derived from JWT, never a query param); accept
  optional `project_id` (scopes to that project's linked repos) and optional `repository`
  (further narrows to one repo, 404 if it isn't actually linked to that project/org); `400` if
  GitHub isn't connected for the org yet, matching the Phase 54/57 convention for discovery
  endpoints; GitHub API errors propagate as `502` (matching the existing `/jira/projects`
  real-endpoint convention already in this file).
- **Frontend** — `project_id` becomes the primary scope for all three tabs, matching how the
  existing "Linked Repositories" tab already scopes to `selectedProjectId`: a PM looking at
  Project X's GitHub activity shouldn't see Project Y's unrelated PRs. `githubApi.getPullRequests
  /getCommits/getIssues` drop the `orgId` parameter (auth-derived now) and gain `projectId`;
  `useGithubPullRequests/useGithubCommits/useGithubIssues` hooks updated to match;
  `github/page.tsx` re-fetches all three tabs when `selectedProjectId` changes, same pattern
  already used for `linkedRepos`. `DUMMY_ORG_ID` and its now-stale comment are removed.

## Files expected to change

- `backend/app/integrations/github.py` — three new connector methods.
- `backend/app/services/integration.py` — three new service methods.
- `backend/app/api/v1/integrations.py` — rewrite the three endpoints.
- `backend/tests/test_github_real_dashboard_data.py` (new) — real-data checks, GitHub-not-
  connected 400, no-linked-repos empty result, project-scoping, cross-tenant isolation,
  repository-not-linked 404.
- `backend/tests/run_all_tests.py` — register the new suite (Phase 61).
- `frontend/api/github.api.ts`, `frontend/hooks/useGithub.ts`, `frontend/app/github/page.tsx`,
  `frontend/types/github.ts` (only if the response contract needs a small addition, e.g. an
  empty-state distinction) — wire the real, project-scoped data through.

## Test plan

- Real PR/commit/issue data returned for a project with a linked, connected repo (mocked at
  the `httpx.AsyncClient.get` boundary the same way Phases 54/56/57 mock the provider API,
  never the app's own logic).
- GitHub not connected for the org → `400`, no crash.
- Project with zero linked repos → `200` with an empty list, not an error.
- `repository` param naming a repo not linked to the given project → `404`.
- Cross-tenant: Org B can never retrieve Org A's project's PR/commit/issue data by guessing a
  `project_id` (404, matching the established ownership-precheck pattern).
- Master suite stays green (75/75 expected).
