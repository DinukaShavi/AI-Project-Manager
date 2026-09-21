# Phase 60 Plan: Webhook Security Hardening (Per-Org Token URLs)

**Status:** Implemented and verified. 12/12 dedicated security checks passing standalone
(`test_webhook_security.py`); 74/74 master regression suite passing.

## Why this is bigger than the original audit's finding

The audit's P4 finding was "webhook signature verification fails open." Re-verifying the
actual code (`backend/app/api/v1/integrations.py`, `backend/app/services/integration.py`)
surfaced two more issues that make the fail-open bug worse than it looked, and mean fixing it
alone wouldn't actually close the hole:

1. **The verification `secret` is a client-supplied query parameter** on all four webhook
   routes (`secret: Optional[str] = None`, then `webhook_secret = secret or settings.X`).
   A caller can pass their own `secret`, sign the payload with it themselves, and "verification"
   passes — against a secret the attacker chose.
2. **`organization_id` is also a client-supplied query parameter**, with no check that the
   caller has any relationship to that organization at all. Even with (1) fixed, someone with
   a *legitimately* signed webhook from their own GitHub/Slack account could still attribute
   it to a different org's `organization_id`.
3. Credential conflation, found while reading the fallback chain: Jira's fallback secret is
   `settings.JIRA_API_TOKEN` (a real API credential, not a webhook secret) and Google's is
   `settings.GOOGLE_CLIENT_SECRET` (the app's OAuth client secret) — both get compared against
   an attacker-influenced header via `hmac.compare_digest`. Not a direct leak (timing-safe,
   one-way comparison), but architecturally wrong to expose either credential to this surface.

Decision (asked and answered): **per-org secret webhook URL**. Each organization's webhook URL
becomes `/webhooks/{provider}/{webhook_token}` — an unguessable, per-(org, provider) token
generated when the integration connects. The token itself is the primary trust anchor
(identifies *and* authenticates the org); provider signature verification becomes a real
defense-in-depth layer on top of it, not the only line of defense.

## Design

- **Migration**: add `Integration.webhook_token` — `String(64)`, unique, indexed, nullable
  (existing rows get one lazily). Generated via `secrets.token_urlsafe(32)`.
- **Generation point**: `IntegrationService.exchange_code_for_token`, in the existing
  "retrieve or create Integration record" block (`backend/app/services/integration.py:480-495`)
  — set only when a *new* Integration row is created, never rotated on reconnect (rotating
  would silently break whatever's already configured on the provider's side).
- **New router**: `POST /webhooks/{provider}/{webhook_token}` (new top-level path, not nested
  under `/integrations`, since it's no longer organization-scoped-by-query-param). Looks up
  `Integration` by `(provider, webhook_token, is_active=True)` to resolve `organization_id`
  server-side — the request body/headers never get to assert it.
  - Token not found / provider mismatch / inactive integration → `404` (matches the existing
    "no existence leak" convention used elsewhere in this codebase for cross-tenant lookups).
  - If a global per-provider secret **is** configured (`GITHUB_WEBHOOK_SECRET`,
    `SLACK_SIGNING_SECRET`) and a signature header is present → must verify or `401`.
  - If a secret is configured but the signature header is **missing** → `401` (this is the
    actual fail-closed fix; today this case sails through as "unverified but accepted").
  - If no secret is configured server-side at all → accepted on token auth alone. This is
    still a real improvement over today, where neither the token nor a secret exist — token
    possession is now doing genuine authentication work.
  - Jira's and Google's fallback-to-a-real-credential bug is removed outright — verification
    for every provider only ever compares against its dedicated `*_WEBHOOK_SECRET` setting,
    never a credential used for anything else. Jira has no dedicated secret configured today,
    so it runs on token-auth-only for now (same as GitHub/Slack when unconfigured) — a real
    `JIRA_WEBHOOK_SECRET` setting is added so it can be turned on later without more code
    changes.
- **Old routes removed**: `POST /integrations/{github,jira,slack,google}/webhook` (with
  `organization_id`/`secret` query params) are deleted, not deprecated-in-place — leaving them
  reachable would defeat the fix.
- **New read endpoint**: `GET /integrations/{provider}/webhook-url` — admin-gated (`ADMIN_ROLES`,
  matching `external_identity.py`'s convention), tenant-scoped, returns the org's real
  `/webhooks/{provider}/{token}` URL so a PM can actually configure it on GitHub/Jira/Slack/
  Google's side. Without this the feature is unusable — there'd be no way to discover the URL.
  404s if the org hasn't connected that provider yet (no Integration row = no token to show).
- **Frontend**: a small "Webhook URL" read-only field + copy affordance added to the existing
  Connected Accounts panel (`frontend/app/settings/page.tsx`) per connected provider — the
  minimum needed for this to be a usable, complete vertical slice, not a wider redesign.
- **`receive_webhook`'s signature stays the same** (`organization_id` param, called internally)
  — only the router layer above it changes how `organization_id` gets resolved.

## Explicitly out of scope for this turn

- Token **regeneration** (rotate a leaked token) — real need, but a separate, self-contained
  admin action; noted as a fast-follow, not bundled here.
- Migrating the mock GitHub/Jira/Slack dashboard reads (roadmap Steps 2–4) — unrelated surface,
  already sequenced separately in `docs/master_completion_roadmap.md`.

## Files expected to change

- New Alembic migration: add `Integration.webhook_token`.
- `backend/app/models/integration.py` — add the column.
- `backend/app/core/config.py` — add `JIRA_WEBHOOK_SECRET: Optional[str] = None` (parity with
  the other three providers; currently missing entirely).
- `backend/app/services/integration.py` — generate `webhook_token` on Integration creation;
  new `resolve_organization_for_webhook_token(provider, webhook_token)`; new
  `get_webhook_url(organization_id, provider)`; `receive_webhook` unchanged internally.
- `backend/app/api/v1/integrations.py` — remove the four old query-param webhook routes;
  the four `verify_webhook_signature` global-secret settings move with them.
- New `backend/app/api/v1/webhooks.py` (or added to `integrations.py` under a new prefix) —
  the four new `POST /webhooks/{provider}/{webhook_token}` routes, and the
  `GET /integrations/{provider}/webhook-url` read endpoint.
- `backend/app/api/v1/router.py` — register the new router if split into its own file.
- `frontend/app/settings/page.tsx`, `frontend/api/organization.api.ts` (or a small new
  `integrations.api.ts` addition) — webhook URL display.
- `backend/tests/test_integrations.py` — existing webhook tests currently pass *because* of
  the fail-open bug (no signature, no secret, org_id trusted from the query string); these get
  rewritten to use the new token-based routes with real signatures, not weakened.
- New `backend/tests/test_webhook_security.py` — the actual security-regression suite for this
  phase (see below).
- `backend/tests/run_all_tests.py` — register Phase 60.

## Test plan

- Valid token → `202`, event correctly attributed to the token's real owning org (not a
  caller-supplied one).
- Unknown/malformed token → `404`, no event created.
- A provider-mismatched token (Org A's GitHub token against the Slack route) → `404`.
- Global secret configured + missing signature header → `401`, no event created (the actual
  "prove the fail-open bug is fixed" check — mirrors this session's established pattern of
  reverting a fix to confirm the test catches it, then restoring).
- Global secret configured + invalid signature → `401`, no event created.
- Global secret configured + valid signature → `202`, accepted.
- No global secret configured (today's actual `.env` state) → still `202` via token auth alone.
- `GET /webhook-url` — real URL returned for a connected provider; `404` for an unconnected
  one; non-admin caller rejected; cross-tenant (Org B can never retrieve Org A's token/URL).
- Old routes are gone: requesting the deleted paths returns `404`/`405`, not the old behavior.
- Master suite stays green (74/74 expected).
