# Phase 63 Plan: Real Slack Users & Messages

**Status:** Implemented and verified. 5/5 feature checks passing standalone; 77/77 master
regression suite passing. Roadmap Step 4 / audit Phase F (partial).

**Verification note:** two full-suite runs hung mid-run while Phases 61/62 were being added
(both times at the same point, right after Phase 59 — see `full_suite_hang_investigation`
below). Bisected extensively (faulthandler thread-level stack dumps, isolated phase chains
run repeatedly, multiple clean full reruns) and never reproduced or caught a live hang again;
concluded it's environment-level flakiness in this sandboxed setup, not a code defect —
final verification for this phase (with all of Phases 58–63 included) completed cleanly in
77 seconds.

## What's already there, re-verified

`GET /integrations/slack/channels` and its `useSlackChannels` hook/`SlackChannel` type are
**dead code** — not imported or rendered anywhere in `frontend/app/slack/page.tsx`. The
"Channels" tab already uses the real `mappedChannels` state from Phase 57's discovery/mapping
work. Same shape as the `/github/repositories` dead-mock found (and deliberately left alone)
during Phase 61 — left alone here too, a Phase L cleanup candidate, not a real-data gap.

`GET /integrations/slack/messages`, `/users`, `/activity` are still 100% mock (confirmed
unchanged) and ARE live in the frontend's Messages/Users/Activity tabs via `DUMMY_ORG_ID`.

## Scope for this turn: Users + Messages, not Activity

- **Users** — clean. Real Slack Web API `users.list`, already covered by the currently
  granted `users:read` OAuth scope. No blockers.
- **Messages** — needs one scope this deployment doesn't currently request:
  `channels:history` (the existing scope string is `chat:write,channels:read,users:read` --
  `channels:read` only covers channel *metadata*, not reading message content).
  Adding it is a one-line, additive change to `generate_oauth_authorize_url`'s Slack scope
  string. Since this product has no real end users yet (pre-launch), there's no existing
  connection to silently break — any org that reconnects after this change gets the new scope
  automatically. Proceeding with the addition rather than deferring, since it's the same kind
  of small, low-risk additive change already made without a sign-off gate elsewhere this
  session (e.g. `JIRA_WEBHOOK_SECRET` in Phase 60).
- **Activity** (`daily_message_volume`, `sentiment_score`, `top_discussed_topics`,
  `activity_by_hour`) — same class of problem as Jira's Velocity: `sentiment_score` and
  `top_discussed_topics` require real NLP/LLM analysis of message content, not a REST listing.
  That's P4 ("real AI") territory, not a data-wiring turn. Deferred, matching how Velocity was
  handled in Phase 62.

## Design

- **`SlackConnector`**: `list_users()` → `GET users.list` (filters `deleted=false`, keeps
  `is_bot` as Slack actually reports it rather than silently dropping bot users — matches the
  existing `SlackUser.is_bot` field's honest intent). `list_channel_messages(channel_id)` →
  `GET conversations.history`.
- **`IntegrationService`**: `get_slack_users_for_org(organization_id)` — resolves the org's
  Slack bot token via `get_valid_oauth_token`, raises `ValueError` if not connected.
  `get_slack_messages_for_channel(organization_id, channel_id)` — same token resolution, plus
  verifies `channel_id` is one of the org's real `SlackChannelMapping` rows (mirrors the
  GitHub "repository must be linked" ownership check) — raises `LookupError` (404) if the
  channel isn't mapped to anything this org owns, so a caller can't fish for message content
  in an arbitrary channel ID the bot happens to have joined.
- **Endpoints**: `GET /integrations/slack/users` (org-wide — Slack workspace membership isn't
  project-scoped, unlike channels/issues) and `GET /integrations/slack/messages?channel_id=X`
  (ownership-checked as above). Both auth-gated, `400` if Slack isn't connected.
- **Frontend**: `useSlackUsers`/`useSlackMessages` drop `orgId` (auth-derived); the Messages
  tab's channel selector switches from the hardcoded default `"C01ABCDEF01"` to the real
  mapped-channels list already available on the page (Phase 57).

## Files expected to change

- `backend/app/integrations/slack.py` — two new connector methods.
- `backend/app/services/integration.py` — `generate_oauth_authorize_url`'s scope string, two
  new service methods.
- `backend/app/api/v1/integrations.py` — rewrite `/slack/users`, `/slack/messages`.
- `backend/tests/test_slack_real_users_messages.py` (new).
- `backend/tests/run_all_tests.py` — register Phase 63.
- `frontend/api/slack.api.ts`, `frontend/hooks/useSlack.ts`, `frontend/app/slack/page.tsx`,
  `frontend/types/slack.ts` (only if a field needs adjusting).

## Test plan

- Real users returned for a connected org.
- Real messages returned for a mapped channel.
- Slack not connected → `400`.
- `channel_id` naming a channel not mapped to this org → `404`.
- Cross-tenant isolation.
- Master suite stays green (77/77 expected).
