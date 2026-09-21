# Phase 84 Plan: Require Authentication on the 6 Remaining Unauthenticated Routers

**Status:** Implemented and verified. The 6 lower-severity findings deferred at the end of
Phase 83's full-project sweep (the user explicitly chose to fix only the 3 highest-severity
findings that turn) -- continuing "continue" closed this remaining, already-tracked item.
`Depends(get_current_user)` added to all 16 endpoints across the 6 routers; the 6 dedicated
test suites and `test_frontend_api_contract.py` all updated to authenticate and to assert an
unauthenticated request is rejected, and all pass standalone. Master regression suite: **89/89
passing**. One background run of the full suite stalled for 35+ minutes at the same point
(Phase 77's real GitHub API test) with zero log progress -- the same class of non-reproducible
environment flakiness documented earlier in this engagement (Phases 59-61, and again in the
Phase 75/76 window); killed via `TaskStop` and a clean re-run passed 89/89 immediately,
confirming it was not a regression from this phase's code.

## What's here and why it's lower severity than Phase 83's three

- `backend/app/api/v1/model_router.py` (`GET /models/matrix`, `POST /models/route`)
- `backend/app/api/v1/observability.py` (`GET /observability/traces`, `GET
  /observability/metrics`, `POST /observability/spans`)
- `backend/app/api/v1/security_guard.py` (`POST /security/scan-prompt`, `POST
  /security/mask-pii`, `POST /security/sanitize`)
- `backend/app/api/v1/rate_limiter.py` (`POST /rate-limit/check`, `GET
  /rate-limit/status/{dimension}/{identifier}`)
- `backend/app/api/v1/prompts.py` (`GET /prompts/{prompt_key}`, `POST /prompts/register`,
  `POST /prompts/outcome`, `POST /prompts/{prompt_key}/rollback`)
- `backend/app/api/v1/evaluations.py` (`POST /evaluations/evaluate-output`, `POST
  /evaluations/benchmark`)

Read all 6 files and their backing engines in full before designing a fix. Unlike Phase 83's
three, **none of these six have any `organization_id`/tenant concept anywhere** -- no request
field, no response field, no per-tenant partitioning in the backing engine. Each backs a
process-global piece of internal platform infrastructure (model routing config, OTel span
buffer, prompt-injection/PII scanner, token-bucket rate limiter, prompt version registry,
agent-evaluation scorer) that every organization's traffic already shares by design -- the
model routing matrix, the rate limiter's buckets, the prompt registry are not meant to be
per-tenant data. Confirmed via grep: **zero frontend callers** (`frontend/`) for any of the
six -- these are internal/engineering-facing endpoints only, reachable through direct API
calls, consistent with `memory_lifecycle.py`'s finding in Phase 83.

So there is no cross-tenant *data* leak risk here (there's no tenant-scoped data to leak) --
the real, narrower gap is exactly what Phase 83's audit callout already named: "still callable
with no login." Fixing that is a real, if lower-severity, hardening step, and matches this
codebase's own standing rule (Phase 83's own design note): nothing in this application should
be callable without authentication.

## Design

Add `Depends(get_current_user)` to every endpoint across all 6 routers -- a login requirement
only, no `organization_id` derivation or resource-ownership check, since these are genuinely
global infrastructure endpoints with no tenant-scoped resource to own. This is a narrower fix
than Phase 83's (which also had to remove client-supplied tenant/privilege fields) because
there is nothing tenant-shaped in any of these six to remove.

## Explicitly out of scope for this turn

- Any RBAC/role gating beyond "must be logged in" -- these are internal tooling endpoints, not
  administrative actions with a documented higher bar; Phase 83's `SuperAdmin`-only bar applied
  specifically to `audit-access` because its own docstring said so. Nothing here claims that.
- Making any of these six per-organization -- would be a real architecture change (e.g. a
  per-org rate limit budget, a per-org prompt registry) beyond "require login," not asked for.
- The remaining deferred items from the same sweep (Sidebar dead-button bug, `ContextSearchTool`
  mock-fallback trap, fabricated RBAC `user_id`, two orphaned models, empty `crud/` package) --
  a separate, unrelated set of findings, left for a future explicit request.

## Files expected to change

- `backend/app/api/v1/model_router.py`, `observability.py`, `security_guard.py`,
  `rate_limiter.py`, `prompts.py`, `evaluations.py` -- add `Depends(get_current_user)`.
- `backend/tests/test_model_router.py`, `test_observability.py`, `test_security_guard.py`,
  `test_rate_limiter.py`, `test_prompt_registry.py`, `test_evaluation_engine.py`,
  `test_frontend_api_contract.py` -- all currently call these routes unauthenticated; update to
  authenticate, and add one unauthenticated-request-rejected assertion per router (matching
  Phase 83's test pattern) rather than only adding auth headers silently.

## Test plan

- Each of the 6 routers: an unauthenticated request to at least one representative endpoint
  gets 401/403, not 200.
- Every existing assertion in the 6 dedicated suites and in
  `test_frontend_api_contract.py` keeps passing once real auth headers are added.
- Master suite stays green (89/89, no new suite files -- extends existing ones).
