# Phase 70 Plan: Wire `agents/page.tsx`'s Execute Agent Button to Real Execution

**Status:** Implemented and verified. Follow-up to the readiness-check update published this
turn, which flagged `agents/page.tsx` as the one item the original audit found broken
(`"Execute Agent"` button with no `onClick`) that no phase in the 52-69 window addressed by
name, and left explicitly unconfirmed rather than assumed fixed. Frontend-only; `npx tsc
--noEmit` clean after both files below changed.

## Verified current state

`frontend/app/agents/page.tsx` is entirely static demo state:
- `personas` is a hardcoded local array, not fetched from anywhere.
- The `<button>` at line 57-59 has no `onClick` at all -- confirmed unchanged from the
  original audit's finding.
- No organization/project context is sourced on the page (no `useAuth`, no project selector),
  unlike every other integration page (`github/page.tsx`, `jira/page.tsx`, `slack/page.tsx`)
  which all follow the same real pattern: `useAuth()` for `organization_id`, then
  `projectApi.getWorkspaces` -> `projectApi.getProjects` for a real project selector.

## A second, more important bug found during investigation

The four hardcoded persona `type` strings on this page --
`TechnicalPMAgent, SprintPlanningAgent, RiskAnalysisAgent, ArchitectureReviewAgent` -- were
checked against `AgentService.get_agent`'s real alias table
(`backend/app/services/agent.py:20-32`), which only recognizes four real, implemented
personas: `TechnicalPMAgent` (`app/agents/tpm.py`), `CodeAnalystAgent`
(`app/agents/code_analyst.py`), `RiskManagerAgent` (`app/agents/risk_manager.py`),
`ArchitectureReviewerAgent` (`app/agents/architect.py`).

Three of the four strings on this page do not match any alias and would raise
`ValueError: Unknown agent type` the moment they were wired to the real endpoint:
- `SprintPlanningAgent` -- no such persona exists anywhere in the backend at all.
- `RiskAnalysisAgent` -- real persona is `RiskManagerAgent` (aliases: `risk_manager`,
  `riskmanageragent`, `risk`); `riskanalysisagent` matches none of them.
- `ArchitectureReviewAgent` -- real persona is `ArchitectureReviewerAgent` (missing "er");
  `architecturereviewagent` matches none of the real aliases either.

The pre-existing `AgentActionsConsole.tsx` component had the same bug for its Calendar action
(`executeAgentPersona("SprintPlanningAgent", ...)`, would be rejected by
`backend/app/services/agent.py`) -- same root cause, different component, not the one the
audit flagged by name, but cheap to fix in the same pass rather than leaving it for a future
session to rediscover independently. Fixed by switching that one call to `"TechnicalPMAgent"`
(its Slack and PR-comment actions already used a real type). Its `workflows/page.tsx` sibling
uses `SprintPlanningAgent`/`RiskAnalysisAgent`/`ArchitectureReviewAgent` too, but only as
descriptive label text inside a `workflow template` id/name/agents object -- the actual
executed value is the template `id` (`sprint_planning`, `pr_review`, `risk_assessment`) passed
to `workflowApi.executeWorkflow`, not a raw `agent_type` string, so it's not the same bug and
was left alone.

## Design

- Replace the fictional `SprintPlanningAgent` persona card with `CodeAnalystAgent` (real,
  currently not represented anywhere in this page's UI), and correct the other two type
  strings to their real values (`RiskManagerAgent`, `ArchitectureReviewerAgent`) -- four cards,
  four real personas, exact match to `AgentService.get_agent`'s aliases.
- Add the same real org/project sourcing pattern already used on `github/page.tsx`:
  `useAuth()` -> `organization_id`; `projectApi.getWorkspaces` + `projectApi.getProjects` ->
  a real project selector. The Execute Agent buttons are disabled until a real project is
  selected, mirroring `AgentActionsConsole`'s `canExecute` guard.
- Each card's Execute Agent button calls the real `agentApi.executeAgentPersona` (already a
  live, tested endpoint -- `POST /agents/execute` -- used elsewhere in the app, e.g.
  `app/page.tsx:189` and `AgentActionsConsole.tsx`), passing the card's own `agent_type` and a
  fixed, honestly-labeled task string per persona (e.g. TPM -> "Analyze current sprint
  velocity and task bottlenecks", Code Analyst -> "Review recent commits and pull requests for
  code quality issues", etc. -- reusing the real per-persona focus already described in each
  card's existing `description` text rather than inventing new copy).
- Per-card loading/result state (mirrors `AgentActionsConsole`'s existing loading/result
  pattern) -- the "State: IDLE / READY" label updates to reflect a real in-flight/completed
  state, and the real `output.analysis` (or an error message) renders inline under the card
  once the call resolves.

## Explicitly out of scope for this turn

- A real execution-history list. The page header text mentions "execution history," but no
  `GET /agents/executions` (list) endpoint exists -- only `GET /agents/executions/{id}`
  (single, Phase 69). Building a list endpoint is new backend work disproportionate to what
  this phase is fixing (a broken button), not a natural extension of it. Flagged for a future
  phase if wanted.
## Files changed

- `frontend/app/agents/page.tsx` -- real org/project sourcing (matches `github/page.tsx`'s
  pattern), corrected 4-persona list (`TechnicalPMAgent`, `CodeAnalystAgent`,
  `RiskManagerAgent`, `ArchitectureReviewerAgent`), real execution wiring via
  `agentApi.executeAgentPersona`, per-card loading/result/error state.
- `frontend/components/agent-dashboard/AgentActionsConsole.tsx` -- one-line fix, Calendar
  action's `agent_type` corrected from `"SprintPlanningAgent"` to `"TechnicalPMAgent"`.
- No backend changes -- `POST /agents/execute` already does everything needed once called with
  a valid `agent_type`.

## Test plan

Frontend-only change against an already-tested real backend endpoint (Phase 69's suite
already proves `POST /agents/execute` end-to-end for all four real personas). Verification
here is `npx tsc --noEmit` clean, plus a manual check that all four corrected type strings
match `AgentService.get_agent`'s alias table exactly (done above, by direct code comparison --
no new backend test needed since no backend code changes).
