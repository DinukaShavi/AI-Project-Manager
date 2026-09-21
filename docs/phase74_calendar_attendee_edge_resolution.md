# Phase 74 Plan: Resolve Calendar's ATTENDS Graph Edges to Real Users

**Status:** Implemented and verified. Extended Phase 73's test suite (now 4/4 checks, including
a real matched-attendee resolution and a real cross-tenant non-match); 85/85 master regression
suite passing. Follow-up to Phase 73, which added a real `ATTENDS` knowledge-graph
edge per meeting attendee but URN'd every attendee by their raw email
(`urn:user:email:{email}`) — real, but not yet correlated with the org's own real `User` rows,
even when the attendee genuinely is one.

## What's already there, re-verified

`_extract_graph_edges` (`backend/app/services/context_ingestion.py`) is a synchronous, DB-free
method today -- deliberately, since GitHub's `urn:github:user:{login}` and Jira's
`urn:jira:user:{account_id}` edges both already use the *external* provider identifier as the
node URN, not a resolved internal `User.id`. Calendar's raw-email URN is actually consistent
with that existing pattern, not an outlier -- so this phase isn't "fixing an inconsistency,"
it's a genuine enhancement Calendar can support that GitHub/Jira can't as directly: a Calendar
attendee's email *is* the org's own real login identifier (`User.email`), a direct match,
whereas resolving a GitHub login or Jira account id to a real `User` would need the
`ExternalIdentity` table (Phases 53-55) and is a separate, larger piece of work -- explicitly
out of scope here, noted below for later.

## Design

- `_extract_graph_edges` becomes `async def`, gaining two optional parameters:
  `session: Optional[AsyncSession] = None`, `organization_id: Optional[UUID] = None`. GitHub
  and Jira branches are unchanged (still don't touch the DB). The calendar branch, when both
  are provided, looks up each attendee email against `User` scoped to the org
  (case-insensitive) before building the edge:
  - Match found -> `urn:user:id:{user.id}` (a real, internal AI-TPM user).
  - No match -> `urn:user:email:{email}` (unchanged fallback -- a real external attendee who
    isn't an AI-TPM user, which is an expected, honest outcome, not a failure).
- `handle_event`'s call site becomes `edges = await self._extract_graph_edges(provider,
  payload, session=session, organization_id=organization_id)` -- `session` is already open in
  that scope (the same one used for indexing/graph-edge writes two lines later), so no new
  session is opened.

## Explicitly out of scope for this turn

- Resolving GitHub `urn:github:user:{login}` / Jira `urn:jira:user:{account_id}` edges to real
  `User` rows via `ExternalIdentity` -- a real, valuable, and separate enhancement (needs a
  join through `ExternalIdentity.provider_user_id`, not a direct field match like email), not
  bundled into this smaller Calendar-specific fix.

## Files expected to change

- `backend/app/services/context_ingestion.py` -- `_extract_graph_edges` signature + calendar
  branch.
- `backend/tests/test_calendar_context_ingestion.py` -- extend Test 2 to cover both a real
  matched attendee (real `User` row with that email) and a real external attendee (no matching
  `User`), asserting the correct URN scheme for each.
- `backend/tests/run_all_tests.py` -- no new suite registered (extends the existing Phase 73
  suite).

## Test plan

- An attendee whose email matches a real `User` in the org produces an edge targeting
  `urn:user:id:{user.id}`.
- An attendee with no matching `User` (external participant) still produces an edge, targeting
  `urn:user:email:{email}` -- unchanged behavior, not silently dropped.
- Cross-tenant: an attendee email matching a `User` in a *different* organization does not
  resolve (the lookup is org-scoped) -- falls back to the email URN.
- Master suite stays green (85/85 expected -- no new suite, existing one extended).
