# Phase 72 Plan: Real Jira Workload/Velocity & Slack Activity (the deferred AI/NLP cluster)

**Status:** Implemented and verified. 6/6 feature checks passing standalone (including exact
hand-computed workload shares, velocity history/average, and hour-bucketed activity counts);
84/84 master regression suite passing. `npx tsc --noEmit` clean on all frontend changes.
Closes the last mock-dashboard cluster named in the readiness audit
and the master roadmap's "Recommended Next Step" -- `GET /jira/workload`, `GET /jira/velocity`,
`GET /slack/activity`, all still 100% hardcoded and unauthenticated
(`organization_id: Optional[UUID] = None` + `DEFAULT_ORG_ID` fallback, no
`Depends(get_current_user)`), confirmed unchanged by re-reading
`backend/app/api/v1/integrations.py` directly rather than trusting the deferral note in
Phase 62/63's docs.

## What's already there, re-verified -- the deferral reasoning was half-stale

Phase 62/63 deferred all three specifically because Story Points is a per-instance custom
field with no fixed id, and Jira's Velocity Chart has no public REST equivalent. Re-reading
`backend/app/integrations/jira.py` and `backend/app/services/integration.py` (both untouched
since Phase 62) shows the harder half of that problem was already solved as a *building
block*, just never wired to an endpoint:

- **`JiraConnector.resolve_story_points_field_id()`** (`jira.py:148-162`) -- real best-effort
  field resolution, already used by `get_jira_issues_for_project` and
  `get_jira_sprints_for_project`.
- **`get_jira_issues_for_project`** (`integration.py:958-978`) already returns each real
  issue's `assignee` and nullable `story_points` -- everything Workload needs is already a
  field on data this project fetches today, just never aggregated.
- **`JiraConnector.get_sprint_story_points(sprint_id, field_id)`** (`jira.py:201-224`) already
  sums real completed vs. total story points per sprint from real issue data (`GET
  /sprint/{id}/issue`), and **`get_jira_sprints_for_project`** (`integration.py:980-1005`)
  already calls it for every sprint it returns -- everything Velocity needs (per-sprint
  committed/completed points, sprint `state`) is already real, already fetched, just never
  aggregated across sprints into a history.

So Velocity's "no public REST endpoint" limitation is real for a single-call Velocity *Chart*
API, but a real equivalent reconstructed from real per-sprint issue data was already 90% built
by Phase 62 for an unrelated reason (Sprints' own per-sprint story points). This phase is
mostly aggregation over already-real data, not new Jira integration work.

Slack Activity is different: `daily_message_volume` and `activity_by_hour` are real,
deterministic computations over already-real message data (`get_slack_messages_for_channel`,
Phase 63) -- no NLP needed for those two fields, and the original mock's naming/shape mostly
carries over. `sentiment_score` and `top_discussed_topics` are the one piece that genuinely
needs real NLP, as Phase 63's deferral said.

## Design

### Jira Workload -- `IntegrationService.get_jira_workload_for_project`

Aggregates `get_jira_issues_for_project`'s existing output by `assignee` (blank -> `"Unassigned"`):
`assigned_issues` (count), `total_story_points` (sum of the group's numeric `story_points`;
`None`, not a fabricated `0`, when the site's Story Points field couldn't be resolved at all --
same honesty rule Phase 62 already established for the per-issue field).

The original mock's `capacity_percentage` is **dropped, not carried forward** -- it implied an
assumed per-person velocity/capacity baseline that doesn't exist anywhere in this system
(nothing tracks a person's sprint capacity), so it could only ever have been a fabricated
number. Replaced with `percentage_of_team_points`: this assignee's share of the project's total
resolved story points, a real, honestly-computable relative distribution
(`assignee_points / sum(all assignees' points) * 100`) that serves the same "who's carrying
how much" purpose without asserting a capacity number nothing backs.

### Jira Velocity -- `IntegrationService.get_jira_velocity_for_project`

Aggregates `get_jira_sprints_for_project`'s existing output: filters to `state == "closed"`
sprints where `total_story_points` resolved (not `None`), sorted chronologically, most recent
6 kept as `sprint_velocity_history` (`{"sprint": name, "committed": total_story_points,
"completed": completed_story_points}` -- identical shape to the original mock). `average_velocity`
is the mean `completed_story_points` across those sprints, `None` if none qualify (no closed
sprints yet, or Story Points unresolvable on this site) -- never a fabricated placeholder
number.

### Slack Activity -- new `app/services/slack_activity.py`, `SlackActivityService`

- `compute_activity_by_hour(messages)` -- real, deterministic: buckets each message's real
  `timestamp` (already ISO-parsed by `get_slack_messages_for_channel`) by UTC hour. No LLM
  involved.
- `analyze_sentiment_and_topics(messages)` -- the one genuinely new NLP piece. A minimal
  `BaseAgent` subclass (`_SentimentLLM`, same carrier pattern as Phase 71's `_PlannerLLM` --
  exists purely to reuse `_llm_call`'s real Claude/GPT-4o failover, not a new provider-calling
  path) is prompted with the channel's real recent message text and asked for a JSON object:
  `{"sentiment_score": <0.0-1.0>, "top_topics": [...]}`. Parsed and range-validated before
  acceptance; returns honest `{"sentiment_score": None, "top_discussed_topics": []}` -- never
  a fabricated fixed number -- when there are no messages, the LLM is unconfigured, the call
  fails, or the response doesn't parse as valid JSON in range. Same fallback discipline as
  Phase 71's plan decomposition, just for a smaller output shape (one score + a topic list
  instead of a step DAG).
- **Found during investigation, worth flagging, not fixing here:** `ModelRouter.ROUTING_MATRIX`'s
  `CONTEXT_ANALYSIS` category (`gemini-1-5-flash` / `llama-3-8b`) -- the semantically obvious
  choice for this task -- routes to providers `BaseAgent._call_provider_model` has *no real call
  implementation for at all* (only `claude*`/`gpt*` prefixes are wired); selecting it would
  silently and permanently fall through to the synthetic-text fallback regardless of API keys.
  Same is true for `SEARCH_RERANKING` and `ENTITY_EMBEDDINGS`. `_SentimentLLM` therefore uses
  `task_category="output_reflection"` (real Claude 3.5 Sonnet / GPT-4o, same route Phase 71
  uses) instead -- an imperfect semantic fit, but the only two categories (`dag_generation`,
  `output_reflection`) that actually reach a real provider today. Fixing the other three
  routes' provider wiring is out of scope for this phase.
- `GET /slack/activity` becomes channel-scoped (`?channel_id=X`), matching `/slack/messages`'s
  existing real pattern exactly (Phase 63) instead of the old org-wide mock -- Slack activity is
  inherently a per-channel concept once it's backed by real messages, since a project's mapped
  channel is where its real discussion lives.

### Endpoints

All three routes switch from `organization_id: Optional[UUID] = None` (client-suppliable,
`DEFAULT_ORG_ID` fallback, no auth) to the same real, tenant-scoped pattern already used by
`/jira/issues`, `/jira/sprints`, `/slack/messages`: `Depends(get_current_user)`, org derived
from the JWT, `LookupError` -> 404, `ValueError` -> 400. This closes the audit's repeatedly-
flagged "inconsistent posture" gap (§8/§10) for these specific three routes -- the last ones
still open.

## Explicitly out of scope for this turn

- Rewiring `CONTEXT_ANALYSIS`/`SEARCH_RERANKING`/`ENTITY_EMBEDDINGS` to real provider
  implementations -- found during investigation, a real gap, but a separate, broader concern
  than this phase's endpoints.
- Any change to `JiraConnector` or `SlackConnector` -- every building block this phase needs
  already exists from Phases 62/63; this phase is aggregation and one new NLP call, not new
  integration plumbing.

## Files expected to change

- `backend/app/services/integration.py` -- `get_jira_workload_for_project`,
  `get_jira_velocity_for_project`.
- `backend/app/services/slack_activity.py` (new) -- `SlackActivityService`.
- `backend/app/api/v1/integrations.py` -- rewrite `/jira/workload`, `/jira/velocity`,
  `/slack/activity`.
- `frontend/types/jira.ts` -- `JiraTeamWorkload.total_story_points: number | null`,
  `capacity_percentage` -> `percentage_of_team_points: number | null`;
  `JiraVelocityMetrics.average_velocity: number | null`.
- `frontend/types/slack.ts` -- `SlackActivityAnalysis.sentiment_score: number | null`,
  `daily_message_volume` -> `message_count`.
- `frontend/api/jira.api.ts`, `frontend/hooks/useJira.ts`, `frontend/app/jira/page.tsx` --
  `getWorkload`/`getVelocity`/`useJiraMetrics` become project-scoped (matches
  `useJiraIssues`/`useJiraSprints`'s existing pattern), null-safe rendering.
- `frontend/api/slack.api.ts`, `frontend/hooks/useSlack.ts`, `frontend/app/slack/page.tsx` --
  `getActivityAnalysis`/`useSlackActivity` become channel-scoped, null-safe rendering.
- `backend/tests/test_jira_velocity_workload_slack_activity.py` (new).
- `backend/tests/run_all_tests.py` -- register Phase 72.

## Test plan

- Real Workload: per-assignee counts/points match a hand-computed aggregation of seeded real
  issues; `percentage_of_team_points` sums to ~100 across assignees; unresolvable-field case
  returns `None` points, not `0`.
- Real Velocity: `sprint_velocity_history` only includes closed sprints with resolved points;
  `average_velocity` matches a hand-computed mean; no-qualifying-sprints case returns `None`.
- Real Slack Activity: `activity_by_hour`/`message_count` match a hand-computed bucketing of
  seeded real messages; sentiment/topics call exercises the real fallback path in this key-less
  environment (honest `None`/`[]`, not a crash, not a fabricated number) -- same two-tier
  verification approach Phase 71 used for the planner LLM path.
- All three routes: unauthenticated request rejected; not-connected -> 400; unmapped/
  unconfigured project or channel -> 404; cross-tenant isolation.
- Master suite stays green (84/84 expected).
