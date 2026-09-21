# Phase 77 Plan: Broaden the Real Tool-Action Set

**Status:** Implemented and verified. 6/6 feature checks passing standalone (registry discovery,
real GitHub comment, approval-gated real merge, real ADF-wrapped Jira create/comment, real
Slack thread reply with a non-regression check on plain post_message); 87/87 master suite
passing. Found and fixed one pre-existing test whose assumption this phase invalidated:
`test_tool_registry.py`'s Test 7 asserted `merge_pull_request` would 404 (not registered) even
after approval -- true before this phase, false after; updated to assert the approval gate is
bypassed and real execution is attempted (gracefully reporting "not connected" for a fresh
test org with no GitHub link, since the fully-mocked real-API path is this phase's own suite's
job). First of three phases (agreed plan: broaden real actions → real search
reranking → Calendar push-based real-time) aimed at the two lowest-scoring categories in the
readiness audit -- Centralized actions (55) and Workflows (60) -- both capped by the same root
cause: the AI can only take 3 real write actions today (Jira status-transition, GitHub
issue-create, Slack post-message). This phase adds 5 more, doubling the real action set.

## What's already there, re-verified

The tool framework itself needs no changes -- it was already built generically:

- `ToolExecutor.HIGH_RISK_SIDE_EFFECT_TOOLS` (`app/tools/executor.py:14-20`) already lists
  `"merge_pull_request"` by name, pre-anticipating this exact tool -- registering a real tool
  with that name automatically gets the existing RBAC + human-approval-gate treatment with zero
  executor changes.
- `HTNPlanner._decompose_with_llm` (Phase 71) already builds its LLM prompt's tool list
  dynamically from `get_tool_registry().list_tools()` -- new tools become available to real
  LLM-driven plan decomposition automatically, no planner changes needed.
- `ToolExecutor.execute_tool`'s RBAC check, approval gate, parameter validation, and audit
  logging are all generic over `tool_name` -- already proven correct by the 3 existing write
  tools' tests.

## Design

Five new `BaseTool` subclasses, following the exact existing pattern in
`github_tools.py`/`jira_tools.py`/`slack_tools.py` (own auth resolution, `validate_parameters`,
try/except returning `{"status": "success"|"error", ...}`, never raising to the caller):

- **`github_comment_on_pr`** (`GitHubCommentOnPRTool`) -- `POST
  /repos/{repo}/issues/{pr_number}/comments` (GitHub's Issues API also handles PR comments).
  Low risk, no approval gate.
- **`merge_pull_request`** (`MergePullRequestTool`) -- `PUT
  /repos/{repo}/pulls/{pr_number}/merge`. Already high-risk per the executor's own pre-existing
  list -- requires a real approval token.
- **`jira_create_issue`** (`JiraCreateIssueTool`) -- `POST /issue`. Jira Cloud's v3 API requires
  `description` in Atlassian Document Format, not plain text (the same format
  `_extract_jira`'s webhook parsing already detects on the *read* side, `context_ingestion.py`
  -- this is the *write* side of that same real format requirement) -- wrapped via a small
  `_to_adf(text)` helper.
- **`jira_add_comment`** (`JiraAddCommentTool`) -- `POST /issue/{key}/comment`, same ADF
  requirement.
- **`slack_reply_in_thread`** (`SlackReplyInThreadTool`) -- reuses `SlackConnector.post_message`
  with a new optional `thread_ts` parameter (one method, not a duplicate connector method) --
  `POST chat.postMessage` with `thread_ts` set replies in-thread instead of posting top-level.

`GitHubConnector` gains `comment_on_pr`/`merge_pull_request`; `JiraConnector` gains
`create_issue`/`add_comment` (+ `_to_adf` helper) on the existing static-credential path (same
auth mode `transition_issue` already uses); `SlackConnector.post_message` gains an optional
`thread_ts` parameter, additive and backward compatible with every existing caller.

All 5 registered in `get_tool_registry()` alongside the existing 6.

## Explicitly out of scope for this turn

- Calendar reschedule/cancel tools -- deliberately deferred to keep this phase's surface to
  GitHub/Jira/Slack (the three providers the narrow-action-set finding was about); Calendar
  already has real create, and its own phase (push-based real-time) is next regardless.
- `deploy_release` / `delete_repository` / `jira_delete_issue` / `slack_broadcast_all` -- the
  other four names already anticipated in `HIGH_RISK_SIDE_EFFECT_TOOLS` -- genuinely
  higher-risk/destructive actions not asked for and not obviously valuable to build speculatively.
- Any change to `HTNPlanner`'s deterministic keyword-template domain methods -- they stay
  minimal by design; the new tools reach real usage through Phase 71's LLM-driven path, which
  already discovers the full registry dynamically.

## Files expected to change

- `backend/app/integrations/github.py` -- `comment_on_pr`, `merge_pull_request`.
- `backend/app/integrations/jira.py` -- `create_issue`, `add_comment`, `_to_adf`.
- `backend/app/integrations/slack.py` -- `post_message` gains optional `thread_ts`.
- `backend/app/tools/github_tools.py` -- `GitHubCommentOnPRTool`, `MergePullRequestTool`.
- `backend/app/tools/jira_tools.py` -- `JiraCreateIssueTool`, `JiraAddCommentTool`.
- `backend/app/tools/slack_tools.py` -- `SlackReplyInThreadTool`.
- `backend/app/tools/registry.py` -- register all 5.
- `backend/tests/test_broadened_tool_actions.py` (new).
- `backend/tests/run_all_tests.py` -- register Phase 77.

## Test plan

- Each of the 5 new tools executes successfully against a mocked real provider API call,
  returning real response data (comment URL, merge SHA, created issue key, comment id, thread
  reply ts).
- `merge_pull_request` without an approval token returns `WAITING_APPROVAL` (proves the
  pre-existing high-risk gate applies to it with zero executor changes); with a token, executes.
- Real ADF wrapping verified for both `jira_create_issue` and `jira_add_comment` (asserted on
  the captured outgoing request body, not just a 200 response).
- `slack_reply_in_thread` asserted to send `thread_ts` in the outgoing payload; a plain
  `slack_post_message` call (unchanged) asserted to NOT send `thread_ts` -- proves the additive
  change didn't alter existing behavior.
- All 5 tools appear in `get_tool_registry().list_tools()` (proves Phase 71's LLM planning path
  picks them up automatically, without re-testing the full LLM decomposition flow again).
- Master suite stays green (87/87 expected).
