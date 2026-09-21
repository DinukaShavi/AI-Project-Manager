# Phase 75 Plan: Resolve GitHub/Jira's ASSIGNED_TO Edges to Real Users

**Status:** Implemented and verified. Extended Phase 59's test suite with 3 new cases (real
GitHub resolution, real Jira resolution, real cross-tenant non-resolution) alongside its 7
pre-existing checks, all 10 passing standalone. Master suite: 85/85 passing on a clean run —
the first full-suite run after this phase stalled with no progress for ~17 minutes, the same
non-reproducible full-suite-only hang documented in Phases 59/60/61 earlier in this
engagement; killed and re-run cleanly per that established precedent, not a code issue (the
same run configuration passed cleanly immediately after). Extends Phase 74's pattern (Calendar's `ATTENDS` edges resolved to
real `User` rows) to GitHub/Jira's `ASSIGNED_TO` edges, explicitly scoped out of Phase 74 as
separate work because it needs a real `ExternalIdentity` join rather than a direct field match.

## What's already there, re-verified

`ExternalIdentity` (Phases 53-55) already links an AI-TPM `User` to their real external
account per provider, keyed by the provider's **stable numeric/opaque account id** -- never an
email, never a username. Confirmed exactly what's stored by re-reading
`IntegrationService._extract_identity_from_token_response` (`integration.py:380-465`):

- GitHub: `external_account_id = str(user["id"])` (the numeric GitHub user id) --
  `external_display_name = user["login"]` (the username is display-only, never a join key).
- Jira: `external_account_id = me["account_id"]` (Jira's `accountId`) -- this is the **exact
  same field** the existing `ASSIGNED_TO` edge extraction already reads off
  `fields.assignee.accountId`, so Jira's resolution is a direct, already-matching join.

`ExternalIdentityService` (`app/services/external_identity.py`) has no reverse lookup yet
(external id -> user) -- only "the caller's own identity" lookups, used by
settings/attendee-resolution flows where the direction is already user -> identity. This phase
adds the missing reverse direction as a new, reusable method.

## Design

- **`ExternalIdentityService.resolve_user_by_external_account(organization_id, provider,
  external_account_id) -> Optional[UUID]`** (new) -- the read side of `link_identity`, a real,
  tenant-scoped, active-only lookup. Small, generically useful (not calendar/GitHub/Jira-
  specific), lives in the service that owns the model, not duplicated inline.
- **`ContextIngestionService._extract_graph_edges`** gains a shared
  `_resolve_user_urn(session, organization_id, provider, external_account_id, fallback_urn)`
  helper: calls the above when `session`/`organization_id`/`external_account_id` are all
  present, returning `urn:user:id:{id}` on a match or the unchanged `fallback_urn` otherwise
  (unresolved is always a real, honest outcome -- an assignee who never connected their
  account, not an error).
- **GitHub branch**: the assignee object already carries both `id` (numeric, matches
  `ExternalIdentity`) and `login` (username, the existing fallback URN's text) in the same
  raw webhook payload -- `assignee.get("id")` is now read alongside `assignee.get("login")`
  and used for the real lookup; the fallback URN text (`urn:github:user:{login}`) is
  unchanged, so an unlinked assignee's edge looks exactly as it did before.
- **Jira branch**: `account_id` is reused directly for both the lookup and the unchanged
  fallback URN (`urn:jira:user:{account_id}`) -- no new field extraction needed.
- This does **not** touch Calendar's `ATTENDS` resolution (Phase 74) -- that's a direct
  `User.email` match, a genuinely different mechanism from an `ExternalIdentity` join, kept
  separate rather than forced through the same helper.

## Explicitly out of scope for this turn

- Slack `ASSIGNED_TO`/similar edges -- Slack messages don't currently carry an assignee
  concept in `_extract_graph_edges` at all (no existing edge type to extend).
- Any change to how `ExternalIdentity` rows get created (Phases 53-55, unchanged).

## Files expected to change

- `backend/app/services/external_identity.py` -- `resolve_user_by_external_account`.
- `backend/app/services/context_ingestion.py` -- `_resolve_user_urn` helper; GitHub/Jira
  branches of `_extract_graph_edges` call it.
- `backend/tests/test_knowledge_graph_ingestion.py` -- extend with a real matched-assignee
  case (a real `ExternalIdentity` linking the webhook's numeric GitHub id / Jira accountId to
  a real `User`) and a real unmatched case (no identity linked -- unchanged fallback URN), for
  both GitHub and Jira.

## Test plan

- A GitHub issue/PR assignee whose numeric id has a real, active `ExternalIdentity` in this
  org resolves to `urn:user:id:{id}`.
- A Jira issue assignee whose `accountId` has a real, active `ExternalIdentity` resolves the
  same way.
- An assignee with no linked identity keeps the exact same fallback URN as before this phase
  (`urn:github:user:{login}` / `urn:jira:user:{account_id}`) -- proves this is additive, not a
  behavior change for the common unlinked case.
- Cross-tenant: an `ExternalIdentity` in a different organization with the same external
  account id does not resolve.
- Master suite stays green (85/85 expected -- no new suite, existing Phase 59 suite extended).
