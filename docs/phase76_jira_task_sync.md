# Phase 76 Plan: Real Jira Issue → ProjectTask One-Way Sync

**Status:** Implemented and verified. 6/6 feature checks passing standalone (create, update-in-
place, status never downgraded on missing category, assignee cleared on unassignment, real
backup-sync payload shape, cross-tenant isolation); 86/86 master regression suite passing. No
frontend changes needed -- `tasks/page.tsx` already renders `jira_issue_key` as a badge when
present, so real synced tasks display correctly with zero UI work. Closes the last item on the
punch list that needed a product
decision (asked via AskUserQuestion): **one-way import, Jira is source of truth** — a real
Jira issue auto-creates or updates a matching `ProjectTask` (title/status/assignee mirror
Jira); edits to the `ProjectTask` itself never push back to Jira.

## What's already there, re-verified

`ProjectTask.jira_issue_key` (`backend/app/models/project.py:38`) already exists as a real
column, settable via `POST /tasks` -- but only ever by a human typing a Jira key in by hand
(`backend/app/api/v1/tasks.py:20,52`). Nothing auto-populates it from a real Jira issue. This
is the exact gap "Jira issues never become `ProjectTask` rows" referred to, and the join key
this phase needs already exists -- no schema change required.

`ContextIngestionService.handle_event` (Phase 58) is, once again, the right choke point: every
real Jira issue -- webhook or 4-hour backup-sync poll -- already passes through it, already
resolves a real `project_id` via `Project.jira_project_key`, and already has the issue's
`summary`/`status`/`issue_key` parsed into `_extract_jira`'s metadata dict. Two pieces of data
this phase needs weren't being carried through to that metadata, though present at the source:

- **Status category.** Jira's `status` field always nests a `statusCategory.key` in
  `{"new", "indeterminate", "done"}` regardless of a project's custom workflow status *names*
  -- the same fixed, small enum `get_sprint_story_points` already keys off for "is this issue
  done" (Phase 62). The real webhook payload already carries it; `run_backup_sync`
  (`integration.py:862-877`) was requesting `assignee`/`status` fields from Jira's API but
  discarding both the assignee and the status category before writing the `Event` payload --
  fixed here to pass both through, not re-fetched.
- **Assignee account id.** Same story: already fetched by `search_recently_updated_issues`'s
  existing `fields=...,assignee,...` request, discarded before this phase.

## Design

- **`_extract_jira`'s metadata dict** gains `status_category` and `assignee_account_id` for
  both the webhook path (`fields.status.statusCategory.key`, `fields.assignee.accountId`,
  already in the raw payload) and the backup_sync path (now passed through from the `Event`
  payload, see above) -- no second parsing pass, same convention `_extract_graph_edges`
  documents for reusing already-parsed data.
- **New `app/services/jira_task_sync.py`, `JiraTaskSyncService.sync_task_from_issue`** --
  small, focused, matches the `ContextSnapshotService`/`SlackActivityService` precedent of a
  dedicated service file per distinct piece of business logic rather than growing
  `IntegrationService` further:
  - Looks up an existing `ProjectTask` by `(organization_id, project_id, jira_issue_key)` --
    project-scoped, matching every other real 1:1 external-entity link in this codebase
    (`Repository`, `SlackChannelMapping`).
  - **Title**: always set to the issue's current `summary` (always present on a real Jira
    issue).
  - **Status**: mapped via `{"new": "todo", "indeterminate": "in_progress", "done": "done"}`.
    Applied on create (falls back to the column's own `"todo"` default if the category is
    unavailable) and on update *only when the category is resolvable* -- an update never
    downgrades a task's status to a guess when real category data is missing, matching this
    engagement's standing "never fabricate" rule.
  - **Assignee**: resolved via `ExternalIdentityService.resolve_user_by_external_account`
    (Phase 75's exact method, reused as-is) from the issue's real `accountId`. Set on both
    create and update, including clearing it back to `None` when Jira's assignee is removed or
    unresolvable -- the direct, honest consequence of "Jira is source of truth": a manual
    reassignment on the `ProjectTask` side that diverges from Jira will be overwritten on the
    next real sync. Documented here explicitly, not a hidden surprise.
  - Never touches `priority` or `story_points` -- out of the agreed scope
    ("title/status/assignee mirror Jira"), left as genuinely `ProjectTask`-owned fields.
- **`ContextIngestionService.handle_event`** calls it once, right where the existing
  graph-edges/snapshot steps already sit, guarded by `provider == "jira" and project_id is not
  None` (a task needs a real project to attach to) -- best-effort, logged on failure, never
  breaks real ingestion.

## Explicitly out of scope for this turn

- Two-way sync (a `ProjectTask` status change transitioning the real Jira issue) -- explicitly
  the option not chosen.
- Manual link-only UI -- explicitly the option not chosen; this phase makes the sync
  *automatic*, not an added manual-attach affordance.

## Files expected to change

- `backend/app/services/integration.py` -- `run_backup_sync`'s `Event` payload gains
  `status_category`/`assignee_account_id` (pass-through of already-fetched data).
- `backend/app/services/context_ingestion.py` -- `_extract_jira` metadata additions;
  `handle_event` calls the new sync service.
- `backend/app/services/jira_task_sync.py` (new) -- `JiraTaskSyncService`.
- `backend/tests/test_jira_task_sync.py` (new).
- `backend/tests/run_all_tests.py` -- register Phase 76.

## Test plan

- A real Jira issue webhook creates a real `ProjectTask` with the right title/mapped status/
  resolved assignee (a real `ExternalIdentity` seeded first).
- A second event for the same issue key updates the existing task in place (title/status/
  assignee change) rather than creating a duplicate.
- An issue with no resolvable status category on update leaves the task's existing status
  untouched (not downgraded to a guess).
- An unassigned/unresolvable-assignee issue clears `assignee_id` back to `None`.
- The real 4-hour backup-sync path (`run_backup_sync`) also produces a real, correctly-synced
  task -- proves the pass-through fix, not just the webhook path.
- Cross-tenant isolation: an issue key that collides with another org's task does not update
  it.
- Master suite stays green (86/86 expected).
