# Master Completion Roadmap

This reconciles the original **AI-TPM Product Readiness Audit** (published artifact,
`c302407a-c0c5-443e-8616-01d1db2de1f3`) against everything actually implemented since —
Phases 52 through 59 of this engagement — and lays out the remaining work, in dependency
order, to close the gap between "partially delivers the vision" and the real thing.

**Process going forward stays the same as it's been since Phase 59**: one plan `.md` per
feature, written and reviewed before implementation starts, added to `docs/`. This document
is the index those per-feature plans hang off of — it doesn't replace them.

Every "still open" claim below was re-verified against the current codebase on 2026-08-22,
not assumed from the original audit text, since a lot has changed underneath it.

---

## 1 · Audit Roadmap (Section 12) Reconciled

| # | Audit's phase | Status | Done in | Evidence |
|---|---|---|---|---|
| A | Wire GitHub repo-linking + Slack channel-mapping UI | **DONE** | Pre-Phase-52 session work | `frontend/app/github/page.tsx`, `frontend/app/slack/page.tsx` real UI |
| B | Org creation + user invitation | **DONE** | Phase 52 | `POST /organizations`, invitation create/list/revoke/accept |
| C | External identity mapping | **DONE** | Phases 53–55 | `ExternalIdentity` model, real GitHub/Slack/Jira identity resolution |
| D | Replace GitHub mock reads with real data | **DONE** | Phase 61 | PR/commits/issues, project-scoped via linked repos |
| E | Replace Jira mock reads with real data | **PARTIAL — DONE** | Phase 62 | Issues + Sprints real, per-org OAuth; Workload/Velocity deferred (Story Points is a per-instance custom field with no fixed id; Velocity has no supported public REST endpoint) |
| F | Replace Slack mock reads with real data | **PARTIAL — DONE** | Phase 63 | Users + Messages real; Activity (sentiment/topics) deferred, needs real NLP (P4 territory) |
| G | Real Event Bus consumer → centralized context | **PARTIAL** | Phases 58–59 | `ContextIngestionService` real; `ContextSnapshot` still has zero writers |
| H | Point Planning/Intelligence at the real graph | **NOT STARTED** | — | `HTNPlanner` still keyword-matches; `"Synthetic reasoning analysis completed..."` still literal |
| I | Calendar write path + attendee resolution | **DONE** | Phases 56, 64 | Real event creation (56) + real teammate resolution via a new self-service member directory (64) |
| J | Real-time push beyond OAuth status | **NOT STARTED** | — | `websockets.py` broadcast still OAuth-status-only |
| K | Webhook signature verification (fail-open fix) | **DONE** | Phase 60 | Turned out to also require closing client-supplied `organization_id`/`secret`; see §3 (historical) |
| L | Frontend cleanup (dead API client functions) | **NOT STARTED** | — | Lowest priority, cosmetic |

Also resolved outside the lettered roadmap: the Jira global-credential-vs-per-org-OAuth
architecture question (P7) was decided by you mid-engagement — **per-organization OAuth**.
Phase 55 implemented the OAuth site/identity resolution side of that decision, but the actual
Jira **read** endpoints (`/jira/projects` real path, `/jira/issues`, `/jira/sprints`, etc.)
still authenticate via the old global static credential. Migrating those onto per-org OAuth
is folded into Phase F below rather than treated as a separate step, since it's the same code
being touched either way.

## 2 · What's Still Mock (verified, not assumed)

Confirmed still present, unchanged, unauthenticated, hardcoded, exactly as the original audit
found — `backend/app/api/v1/integrations.py`:

- `GET /github/pull-requests`, `/github/commits`, `/github/issues`
- `GET /jira/issues`, `/jira/sprints`, `/jira/workload`, `/jira/velocity`
- `GET /slack/channels`, `/slack/messages`, `/slack/users`, `/slack/activity`
- `GET /google/events`, `/google/meetings`, `/google/availability` (distinct from the real
  `GET /calendar/meetings` added in Phase 50/56 — these three are older, unauthenticated
  leftovers the audit didn't call out by name but are the same shape of problem)

All still take `organization_id: Optional[UUID] = None` with a `DEFAULT_ORG_ID` fallback and
`Depends(get_db)` only — no `Depends(get_current_user)`. These are the screens a PM actually
looks at every day, per the audit's own framing, and they're unchanged.

## 3 · Live Security Gap (re-verified at the time — since fixed in Phase 60)

`IntegrationService.receive_webhook` (`backend/app/services/integration.py:61-66`):

```python
is_placeholder = not secret or "your_" in secret or "here" in secret
if signature and secret and not is_placeholder:
    is_valid = connector.verify_webhook_signature(payload_bytes, signature, secret)
    if not is_valid:
        raise ValueError(...)
```

Still fails **open**: omit the signature header, or leave the provider secret unconfigured
(the common case in this environment), and verification is skipped entirely — payload is
ingested unconditionally. Combined with the still-unauthenticated mock read endpoints in §2,
this is a live gap, not just an incompleteness gap. It has **no dependency on anything else
in this roadmap** — it can be fixed independently, any time, including out of the dependency
order below, if you'd rather prioritize it sooner than its position in §4 implies.

## 4 · Step-by-Step Remaining Plan (dependency order)

### Step 1 — Fix webhook signature verification (fail-closed) — **DONE, Phase 60**
Turned out to require more than the fail-closed fix alone: the verification `secret` and
`organization_id` were both client-supplied query parameters, so both had to be closed
together (see `docs/phase60_webhook_security_hardening.md`). Implemented as per-org
unguessable webhook token URLs (`/webhooks/{provider}/{token}`), replacing the old
`?organization_id=&secret=` routes entirely; provider signature verification now fails closed
whenever a real secret is configured. 12/12 security checks + 74/74 master suite passing.

### Step 2 — Replace GitHub mock reads with real data (audit's Phase D) — **DONE, Phase 61**
`/github/pull-requests`, `/github/commits`, `/github/issues` now call the real GitHub API,
scoped to a project's linked repositories (auth-gated, tenant-scoped, project-scoped —
matching the "Linked Repositories" tab's existing scope rather than the whole org). 7/7
feature checks + 75/75 master suite passing. See `docs/phase61_github_real_dashboard_data.md`.

### Step 3 — Replace Jira mock reads with real data (audit's Phase E) — **DONE, Phase 62**
`/jira/issues` and `/jira/sprints` now call the real Jira REST/Agile API via the org's
per-organization OAuth token (Phase 55), replacing the global static credential for these two
reads. Story Points are best-effort resolved (`null`, never a fabricated `0`, when the
per-instance custom field can't be confidently identified). `/jira/workload` and
`/jira/velocity` are explicitly deferred as Step 3b — see
`docs/phase62_jira_real_issues_sprints.md` for why (Story Points custom-field ambiguity for
Workload; no supported public REST endpoint for Velocity at all). 6/6 checks passing.

### Step 4 — Replace Slack mock reads with real data (audit's Phase F) — **DONE, Phase 63**
`/slack/users` and `/slack/messages` now call the real Slack Web API (`users.list`,
`conversations.history`, the latter gated on the channel being one of the org's real mapped
channels). `channels:history` scope added to the Slack OAuth grant for this.
`/slack/channels` was found to be dead code (unused since Phase 57's real discovery/mapping
replaced it) and left alone, same treatment as GitHub's dead `/github/repositories`.
`/slack/activity` (sentiment/topics) deferred — needs real NLP, same class of gap as Jira's
Velocity. 5/5 checks passing, 77/77 master suite.

### Step 5 — Retire or replace the three leftover Google mock endpoints — **DONE, Phase 65**
`/google/events` confirmed dead code, left alone (Phase L candidate). `/google/meetings`
retired outright — its purpose is now covered by `GET /calendar/meetings`, which gained a real
`meet_link` (requested via `conferenceDataVersion=1` at creation time, or extracted from
synced pre-existing events). `/google/availability` retired outright, replaced by
`GET /calendar/availability` — real availability computed from Google's `freeBusy.query` API
across the org's real members (Phase 64's directory), using a documented fixed simplification
(1-hour slots, 09:00–17:00 UTC). 5/5 checks passing, 79/79 master suite. See
`docs/phase65_calendar_meet_links_availability.md`.

### Step 6 — ContextSnapshot population (rest of audit's Phase G) — **DONE, Phase 68**
Two decisions asked and answered: (1) trigger — event-driven and throttled, regenerated at
the same `ContextIngestionService.handle_event` choke point Phase 66 already broadcasts from,
at most once per 15 minutes per project, plus a manual on-demand endpoint; (2) summary method
— templated from real structured data (recent `ContextChunk` activity + real
`find_bottleneck_clusters()` output), embedded with the existing Context Engine embedding
generator, deliberately **not** an LLM-narrated summary — no new model-call cost or
dependency. New "Project Snapshot" panel on the main dashboard. 6/6 checks passing, 81/81
master suite. See `docs/phase68_context_snapshot_population.md`.

### Step 7a — Real agent step execution (audit's Phase H, part 1) — **DONE, Phase 69**
`ProjectIntelligenceEngine.process_goal`'s "agent" plan steps now execute via the same real
LLM path `POST /agents/execute` already used (`AgentService.execute_agent` →
`BaseAgent._llm_call`, real Claude/GPT-4o failover) instead of a hardcoded
`"Synthetic reasoning analysis completed..."` string — reusing existing infrastructure rather
than building a second one, per the investigation's finding. Each step now creates a real,
queryable `AgentExecution` row, grounded in real context assembled from the project's real
knowledge-graph subgraph, its latest `ContextSnapshot` (Phase 68), and real semantic search
over indexed `ContextChunk`s (Phase 58). The no-db unit-test path is preserved unchanged by
design. 3/3 checks passing, 82/82 master suite. See
`docs/phase69_real_agent_step_execution.md`.

### Step 7b — Real plan decomposition (audit's Phase H, part 2)
Depends on: Step 7a (now done). `HTNPlanner.decompose_goal` still keyword-matches a goal
string onto one of three fixed step templates ("sprint" → these 4 steps, etc.) — split out
from Step 7a during investigation as a materially larger, riskier undertaking (LLM-driven
decomposition into a validated `PlanStep` DAG, not just making existing steps execute for
real) that deserves its own design pass rather than being a rider on 7a.

### Step 8 — Calendar attendee resolution (rest of audit's Phase I) — **DONE, Phase 64**
Resolves meeting attendees to real AI-TPM org members instead of raw hand-typed email
strings. Built against a new self-service `GET /organizations/members/directory` (the org's
real member list, Phase 52) rather than `ExternalIdentity` (Phase C) — the more directly
relevant real data source for "pick a teammate," since ExternalIdentity links a user to an
*external provider* account, not to their real AI-TPM email. 4/4 checks passing, 78/78 master
suite. See `docs/phase64_calendar_attendee_resolution.md`.

### Step 9 — Real-time push beyond OAuth status (audit's Phase J) — **DONE, Phase 66**
Every real GitHub/Jira/Slack event that flows through `ContextIngestionService` (Phases
58/59) now broadcasts a real `activity_update` over the existing org-scoped WebSocket the
moment it's indexed — reusing `ConnectionManager`, the same mechanism OAuth status updates
already used, rather than a second real-time system. New "Live Activity" panel on the main
dashboard proves it: new PRs/issues/messages appear with no manual refresh. Calendar activity
(polling-driven, not event-bus-driven) and a durable/persisted feed for reconnecting clients
are both explicitly out of scope — see `docs/phase66_realtime_activity_push.md`. 3/3 checks
passing, 80/80 master suite.

### Step 10 — Frontend cleanup (audit's Phase L) — **DONE, Phase 67**
All 21 originally-flagged dead functions removed (none had been wired up since the original
audit), plus the legacy `integrations.api.ts` file, `lib/api.ts` trimmed from 15 exports to
its 2 real callers, the three newly-dead github/slack/calendar items (with their backend mock
routes also retired, matching Phase 65's precedent), and one orphaned component
(`RepositoryList.tsx`) found during verification. `tsc --noEmit` clean, 80/80 master suite.
See `docs/phase67_dead_frontend_code_cleanup.md`.

---

### Step 11 — Wire `agents/page.tsx`'s Execute Agent button — **DONE, Phase 70**
The original audit's one flagged-broken item that no phase in 52-69 had touched by name: the
"Execute Agent" button had no `onClick` at all, and the page's 4 hardcoded persona `type`
strings didn't even match `AgentService.get_agent`'s real aliases (3 of 4 would have raised
`Unknown agent type` the moment they were wired up -- `SprintPlanningAgent` isn't a real
persona anywhere in the backend). Fixed: real org/project sourcing (same pattern as
`github/page.tsx`), corrected persona list to the 4 real backend personas
(`TechnicalPMAgent`, `CodeAnalystAgent`, `RiskManagerAgent`, `ArchitectureReviewerAgent`), and
real execution via the already-tested `POST /agents/execute`. Same root-cause bug also fixed
in `AgentActionsConsole.tsx`'s Calendar action. Frontend-only, `tsc --noEmit` clean, no new
backend test needed (Phase 69's suite already proves the endpoint). See
`docs/phase70_agents_page_real_execution.md`.

### Step 12 — Real LLM-driven plan decomposition (audit's Phase H, part 2 / Step 7b) — **DONE, Phase 71**
`HTNPlanner.decompose_goal_async` now asks Claude/GPT-4o (via `ModelRouter`'s `DAG_GENERATION`
route -- provisioned in the router since it was built, never actually invoked by anything
until this phase) to produce a goal-specific step plan, replacing the fixed keyword-matched
templates for both real call sites (`ProjectIntelligenceEngine.process_goal`,
`PlanningService.generate_plan`). Every LLM-produced step is validated before acceptance --
real agent persona, real tool name, real tool parameter schema (via each tool's own
`validate_args`), valid DAG (via the existing `WorkflowDAG.validate_dag`) -- and any failure
falls back to the original deterministic template exactly, never a crash or a half-valid plan
reaching execution. The sync `decompose_goal` (keyword-template) is unchanged and now doubles
as the fallback; existing tests that call it directly needed no changes. 5/5 checks passing,
83/83 master suite. See `docs/phase71_llm_plan_decomposition.md`.

### Step 13 — Real Jira Workload/Velocity & Slack Activity (the deferred AI/NLP cluster) — **DONE, Phase 72**
The last mock-dashboard cluster. `Workload` and `Velocity` turned out to be mostly aggregation
over data Phase 62 already fetches for real (`get_jira_issues_for_project`'s per-issue
assignee/story-points, `get_jira_sprints_for_project`'s per-sprint completed/total story
points) -- no new Jira API calls needed. The fabricated `capacity_percentage` was dropped
(nothing in this system tracks a real per-person capacity baseline) and replaced with a real,
honestly-computable `percentage_of_team_points`. Velocity is a real reconstruction from real
per-sprint data, since Jira has no public Velocity Chart endpoint. Slack Activity's
`message_count`/`activity_by_hour` are real deterministic computations over real message
timestamps (Phase 63); `sentiment_score`/`top_discussed_topics` come from a real LLM call
(new `SlackActivityService`, same `BaseAgent._llm_call` carrier pattern Phase 71 used),
honestly `None`/`[]` -- never a fabricated number -- when unavailable. All three routes moved
from unauthenticated `DEFAULT_ORG_ID` fallbacks to the same real, tenant-scoped auth pattern
already used elsewhere. Found and flagged (not fixed): `ModelRouter`'s `CONTEXT_ANALYSIS`/
`SEARCH_RERANKING`/`ENTITY_EMBEDDINGS` routes reference providers with no real call
implementation anywhere -- only `DAG_GENERATION`/`OUTPUT_REFLECTION` (Claude/GPT-4o) are
actually wired. 6/6 checks passing, 84/84 master suite. See
`docs/phase72_jira_velocity_workload_slack_activity.md`.

### Step 14 — Calendar joins the centralized context pipeline — **DONE, Phase 73**
The last integration-shaped gap in "Centralized Context Readiness": Calendar was real
end-to-end but never flowed through `ContextIngestionService`, so calendar activity never
reached the knowledge graph, `ContextSnapshot`, or the real-time activity feed the other three
integrations have shared since Phases 58/59/66/68. Added `_extract_calendar` (no `resolve`
callback needed -- Calendar writes always already know their real `project_id`, unlike
GitHub/Jira/Slack) and a `calendar` branch in `_extract_graph_edges` (one real `ATTENDS` edge
per attendee email). Rather than inventing a fake webhook/Event-row/Outbox detour for a
poll-driven source with no webhook to originate one from, `sync_calendar_events` and
`create_calendar_event` now call `ContextIngestionService().handle_event(...)` directly, right
where each real `Meeting` row is written -- for Calendar, the poll (or the real create-event
call) *is* the ingestion event. Best-effort, never breaks a successful sync/create on failure.
4/4 checks passing, 85/85 master suite. See `docs/phase73_calendar_context_ingestion.md`.

### Step 15 — Resolve Calendar's ATTENDS edges to real Users — **DONE, Phase 74**
Phase 73's `ATTENDS` edges were real but always URN'd every attendee by raw email. Since a
Calendar attendee's email *is* the org's own real `User.email` (a direct match, unlike
GitHub's login or Jira's accountId, which would need a real `ExternalIdentity` join -- a
separate, larger piece of work, left alone here), `_extract_graph_edges` now does a real,
org-scoped `User` lookup for each attendee: a match resolves to `urn:user:id:{id}`; no match
(a genuine external participant) keeps the raw-email URN, unchanged. Proven with a real
cross-tenant case: a `User` with the same email in an unrelated org does not resolve. 4/4
checks passing (extends Phase 73's suite), 85/85 master suite. See
`docs/phase74_calendar_attendee_edge_resolution.md`.

### Step 16 — Resolve GitHub/Jira's ASSIGNED_TO edges to real Users — **DONE, Phase 75**
Extends Phase 74's pattern to the two providers it deliberately left out. `ExternalIdentity`
already links a real `User` to their real GitHub numeric id / Jira accountId (Phases 53-55);
added the missing reverse lookup (`ExternalIdentityService.resolve_user_by_external_account`)
and wired both `_extract_graph_edges` branches through it via a shared `_resolve_user_urn`
helper. A linked assignee's edge now targets `urn:user:id:{id}`; an unlinked assignee's edge
is byte-for-byte unchanged from before this phase (`urn:github:user:{login}` /
`urn:jira:user:{accountId}`) -- purely additive. Proven with a real cross-tenant case: an
`ExternalIdentity` with the same external account id in a different org does not resolve.
10/10 checks passing (extends Phase 59's suite), 85/85 master suite (after killing one
non-reproducible full-suite hang and re-running cleanly -- see phase doc). See
`docs/phase75_github_jira_assigned_to_edge_resolution.md`.

### Step 17 — Real Jira Issue → ProjectTask one-way sync — **DONE, Phase 76**
The last punch-list item that needed a real product decision, asked via AskUserQuestion:
**one-way import, Jira is source of truth**. `ProjectTask.jira_issue_key` already existed as a
column, settable only by hand -- nothing auto-populated it. Now every real Jira issue (webhook
or the 4-hour backup-sync poll) auto-creates or updates a matching `ProjectTask` via the same
`ContextIngestionService.handle_event` choke point every other real event already passes
through: title always mirrors the issue summary; status maps from Jira's fixed
`statusCategory` (`new`/`indeterminate`/`done` → `todo`/`in_progress`/`done`), never downgraded
to a guess when that data is missing; assignee resolves through Phase 75's exact
`ExternalIdentityService.resolve_user_by_external_account`, reused as-is. Found and fixed a
real data-loss bug along the way: `run_backup_sync` was already fetching `assignee`/full
`status` from Jira but discarding both before writing the `Event` payload -- now passed
through. `priority`/`story_points` are left alone as genuinely `ProjectTask`-owned fields, out
of the agreed scope. 6/6 checks passing, 86/86 master suite. See
`docs/phase76_jira_task_sync.md`.

### Step 18 — Investigate ModelRouter's unwired routes — **CLOSED, documentation-only finding**
The last item on the punch list, investigated rather than built. `TaskCategory.CONTEXT_ANALYSIS`
/`SEARCH_RERANKING`/`ENTITY_EMBEDDINGS` (`app/core/model_router.py`) are referenced **only**
inside `model_router.py`'s own definition -- confirmed by a direct grep across the entire
backend, zero real callers anywhere in the application. Separately, `ENTITY_EMBEDDINGS`'s real
purpose is already fully served by a completely different, already-working component:
`get_embedding_generator()` (`app/context/embeddings.py`) makes real OpenAI
`text-embedding-3-small` calls when a key is configured, with an honestly-named
`LocalMockEmbeddingGenerator` fallback -- it has never routed through `ModelRouter` and doesn't
need to. `SEARCH_RERANKING` and `CONTEXT_ANALYSIS` have no shadow implementation either -- no
reranking pass exists in `ContextEngineService.search_context`, no separate large-context
feature exists outside the real Claude/GPT-4o path.

**Decision (asked via AskUserQuestion):** leave as-is, documented as a correct finding rather
than a gap. These are three rows of aspirational routing-table entries for capabilities never
built as features -- wiring real Gemini/Cohere provider calls for them would mean adding new
external API integrations with zero real caller to test against, the one thing this entire
76-phase engagement never did. No code changed. This closes the punch list.

## 5 · Recommended Next Step

**Steps 1–18 are all done** (Phases 60–76, plus Step 18's investigation-only closure). Every
architecturally-significant gap the original audit named — real integrations, real centralized
context now spanning all four providers with every user-node edge resolved to a real internal
user where a link exists, real AI reasoning grounded in that context, a genuinely working
agent-execution UI, real LLM-driven plan decomposition, the last deferred mock dashboards, and
real Jira issues flowing into real `ProjectTask` rows — has a real implementation. **The punch
list is closed.** Nothing remains that this audit's own tracking identifies as a real gap.

Genuinely optional future depth, not tracked as a gap: real search reranking for
`ContextEngineService.search_context` (currently pure vector-similarity ranking, no reranking
pass) would be a real feature improvement, not a fix to anything broken -- surfaced during
Step 18's investigation, not pursued there since it's new scope needing its own design pass.

**Correction (2026-08-23):** "GitHub org-level repo discovery" was carried forward from the
original audit through every revision of this roadmap without being re-verified against
current code. It's real and has been for some time: `GET
/github/discover-repositories` (`backend/app/api/v1/integrations.py:206`,
`IntegrationService.discover_github_repositories`, `integration.py:1125-1150`) calls the real
GitHub `GET /user/repos` API with `affiliation=owner,collaborator,organization_member` --
covering every org the connected token can see, not just the user's own repos -- and is fully
wired to a real "Discover Repositories" flow on `github/page.tsx` (list real repos, one-click
link). No code changed here; this is a correction to a stale claim this document itself kept
repeating, found only because it was re-checked directly against the code rather than trusted
from the prior revision.

None of these block calling this a genuinely centralized, real AI-PM anymore. Recommend
revisiting the audit's other verdicts (Section 9 scores, Section 13 demo-readiness) against
everything shipped since Phase 52 if a fresh readiness check is more useful than more small
cleanup right now, or picking any of the above based on product priority.

## 6 · Depth Phase (post-punch-list)

With the punch list closed, the audit's own score breakdown (17 categories, 0-100) was used to
identify genuine *depth* work -- not gaps, new capability -- targeting the lowest-scoring
categories. Agreed 3-phase plan: broaden real actions → real search reranking → Calendar
push-based real-time.

### Depth Step 1 — Broaden the real tool-action set — **DONE, Phase 77**
Targeted the two lowest audit scores at once (Centralized actions 55, Workflows 60 -- both
capped by the same root cause: only 3 real write actions existed). Added 5 more, following the
exact existing `BaseTool` pattern with zero framework changes needed -- `merge_pull_request`
was already pre-anticipated by name in `ToolExecutor.HIGH_RISK_SIDE_EFFECT_TOOLS`, and Phase
71's LLM plan decomposition already discovers new registry tools dynamically:

- `github_comment_on_pr`, `merge_pull_request` (high-risk, approval-gated) -- new
  `GitHubConnector.comment_on_pr`/`merge_pull_request`.
- `jira_create_issue`, `jira_add_comment` -- new `JiraConnector.create_issue`/`add_comment`,
  correctly wrapping plain text in the Atlassian Document Format Jira Cloud's v3 API requires
  (the write-side counterpart of the ADF *detection* `_extract_jira` already did on the read
  side).
- `slack_reply_in_thread` -- reuses `SlackConnector.post_message` with a new optional
  `thread_ts` parameter, additive and verified non-breaking for the existing top-level-post
  tool.

Found and fixed a pre-existing test whose own assumption this phase correctly invalidated:
`test_tool_registry.py` asserted `merge_pull_request` would 404 after approval (true when
nothing was registered under that name); updated to assert the approval gate is bypassed and
real execution is genuinely attempted. 6/6 checks passing, 87/87 master suite. See
`docs/phase77_broaden_real_tool_actions.md`.

### Depth Step 2 — Real search reranking — **DONE, Phase 78**
Targeted Memory (65). `ContextEngineService.search_context` gained an opt-in `rerank: bool =
False` parameter -- default unchanged, every existing caller keeps its current latency/cost
profile. When `True`, over-fetches a larger real vector-similarity pool (`min(top_k*4, 20)`)
and reranks it via a real LLM call (`_get_reranker_agent`, same `_llm_call` carrier pattern as
Phases 71/72/77), falling back to the original vector order on any failure. Wired into
`ContextSearchTool` -- the concrete tool an AI agent calls when reasoning -- as this phase's
one real consumer; other internal callers (Phase 69's grounding search, Phase 68's snapshot
generation) can opt in later without further plumbing. 5/5 checks passing, 88/88 master suite.
See `docs/phase78_real_search_reranking.md`.

### Depth Step 3 — Calendar faster poll interval — **DONE, Phase 79**
Targeted Real-time events (75). Investigating the original plan ("wire Calendar's existing
push-notification signature verification to trigger a real sync") found the real scope was
materially bigger than framed: no Watch-channel registration exists anywhere
(`events.watch` is never called, so Google has no channel to notify through), no stored
mapping from a notification's `channel_id`/`resource_id` back to which org/project to sync,
and real channels expire (~7 days) needing renewal -- closer in size to Phase 55's OAuth site
resolution than a quick wiring pass. Investigated, explained, and asked (via AskUserQuestion)
rather than either silently downscoping or overbuilding.

**Decision: shorten the poll interval instead.** `CALENDAR_POLL_INTERVAL_SECONDS` changed from
900 (15 min, the original Milestone 10 value) to 120 (2 min) -- a real, meaningful reduction in
staleness via a one-line config change, safe at any interval since the poller's distributed
lock is acquired and released per-cycle (not held for the full TTL). Fixed one pre-existing
test that asserted the specific old value. The full real Watch-channel push option remains a
real, well-scoped future option if ever wanted, not built speculatively. Master suite stays
green (88/88, unchanged suite count). See `docs/phase79_calendar_faster_poll_interval.md`.

**The three-part depth phase is complete** (Phases 77-79): the real action set broadened from
3 to 8, semantic search gained real opt-in reranking, and Calendar staleness dropped from 15
minutes to 2. Every phase either shipped real, tested improvement or was investigated and
explicitly scoped by the user's own decision when the real cost turned out larger than first
framed.

## 7 · Second Grounded Plan (post-depth-phase)

Investigating Analytics (65, the lowest remaining score) directly -- not guessing -- surfaced
a second concrete, evidence-grounded plan: real Monte Carlo forecast inputs → GitHub/Jira
`ASSIGNED_TO` edge resolution → reranking extended to more `search_context` callers.

### Item 1 — Ground the Monte Carlo forecast in real data — **DONE, Phase 80**
`ProjectIntelligenceEngine.process_goal`'s Stage 5 defaulted to hardcoded `[6.0, 7.0, 5.5,
8.0]` velocity / `25.0` remaining points whenever the caller didn't explicitly override them
(the normal case) -- completely disconnected from two real data sources that already existed:
`get_jira_velocity_for_project` (Phase 72) and real `ProjectTask.story_points` sums (Phase
76). `IntelligenceGoalRequest.remaining_points` changed from a pre-resolved `25.0` default to
`Optional[float] = None` so "no override supplied" is representable end-to-end; new
`_resolve_forecast_inputs` looks up real data when available (best-effort, never crashes),
falling back to the original honest example numbers only when neither the caller nor real
project data supplies a value. Added `forecast_data_source` to the response
(`{"velocities": "caller"|"real"|"default", "remaining_points": "caller"|"real"|"default"}`)
for transparency rather than silent substitution. 4/4 checks passing, 89/89 master suite. See
`docs/phase80_real_monte_carlo_forecast_inputs.md`.

### Item 2 — GitHub/Jira `ASSIGNED_TO` edge resolution — **already done (Phase 75), no new work**
Re-verified directly against current code before implementing anything: this was proposed as
item 2 but turned out to already be shipped in Phase 75 (`_resolve_user_urn`, both the GitHub
and Jira branches of `_extract_graph_edges`). Caught and corrected before writing any code,
not silently redone or silently skipped.

### Item 3 — Extend real search reranking to the human-facing search endpoint — **DONE, Phase 81**
Re-checked every real caller of `search_context` directly (not from memory): `ContextSearchTool`
already reranks (Phase 78); `POST /context/search` (the real endpoint a PM's own search bar
calls) didn't. Also caught and corrected a wrong claim in Phase 78's own doc -- "Phase 68's
snapshot generation" was named as a second reranking candidate, but its `_gather_recent_chunks`
is a plain "most recent N" query with no relevance/search concept at all, not a
`search_context` call; reranking doesn't apply there. `POST /context/search` now reranks
(`rerank=True`) since a human directly reads its results and calls are infrequent -- the exact
profile reranking was built for. `_execute_real_agent_step`'s grounding search (Phase 69) was
deliberately left un-reranked and documented as a real cost trade-off (it runs on every agent
step; turning it on would double real LLM calls per step), not silently done or silently
dropped. 1/1 check passing (extends `test_context_engine.py`), 89/89 master suite. See
`docs/phase81_extend_search_reranking.md`.

**This second grounded plan is complete** (items 1 and 3; item 2 needed no new work). Every
`search_context` caller and both Monte Carlo forecast inputs are now either real, explicitly
and transparently deferred for a stated cost reason, or already real from an earlier phase.

### Item 4 — Reranking on the agent-grounding search — **DONE, Phase 82**
The one item Phase 81 explicitly deferred (not built) as a real per-step LLM-cost trade-off.
Closed out on request: `_execute_real_agent_step`'s grounding search (`intelligence_engine.py`,
Phase 69) now reranks too, same mechanism and fallback as Phases 78/81. Real Google Calendar
push notifications remain the one item still declined, not reopened without being asked again
-- an explicit prior decision (Phase 79), not an oversight. 1/1 check passing (extends
`test_real_agent_step_execution.py`; required seeding a second real chunk since reranking
correctly no-ops on a single candidate, caught by the test itself on first run), 89/89 master
suite. See `docs/phase82_agent_grounding_reranking.md`.

**Every item surfaced by either grounded plan is now closed** -- built, or explicitly declined
by the user for a stated reason and left that way.

## 8 · Full-Project Security Sweep — Phase 83

Requested fresh: "scan whole project to find Remaining Gaps" -- a systematic full-project
sweep, not a phase-scoped one. Run as 4 parallel `Explore` agents (backend mock/dead-code,
tenant-isolation security across every router, frontend dead code/broken UI, test-coverage
gaps + orphaned models), each required to cite `file:line` and explicitly report "checked and
clean" to avoid padded findings. Findings personally re-verified by reading all three most
severe files and their backing services in full before designing any fix -- this caught a real
disagreement between the two backend-scan agents (one called `graph_evolution.py`/
`tenant_isolation.py` "not IDOR-shaped" since they're stateless; the other found the real
exploit mechanics underneath: an unbounded singleton with no tenant field, and a trusted
self-declared admin flag) and confirmed the second characterization was accurate.

**User's choice (via AskUserQuestion): fix the 3 security findings now, not the broader scan.**

### Fixed — Phase 83
Three routers had zero authentication and trusted client-supplied identity:
- **`memory_lifecycle.py`** (`/compress`, `/gc`, `/rebuild-index`) -- stateless utility,
  `organization_id` was a plain body field used only as a label; real risk was "callable with
  no login at all," not a per-tenant data leak (no real per-tenant data exists here).
- **`tenant_isolation.py`** (`/partition-keys`, `/validate-vector-query`, `/audit-access`) --
  the third endpoint was the serious one: `is_super_admin` was a **client-supplied boolean**,
  so any caller could claim `is_super_admin: true` and get `allowed: true` for a cross-tenant
  audit on the one endpoint whose entire purpose is enforcing that boundary.
- **`graph_evolution.py`** (`/link`, `/infer`, `/decay-sweep`, `/traverse/{node_id}`) -- the
  real cross-tenant read/write risk: `GraphEdgeRecord` had no `organization_id` field at all,
  so if `source_id`/`target_id` values ever collided across orgs (plausible -- e.g. shared Jira
  key formats), one org's traversal could read another org's edges, and a decay sweep mutated
  every org's weights at once. This is a separate, never-wired-in parallel graph engine, fully
  disconnected from the real DB-backed `ProjectKnowledgeGraph` (Phase 59) -- not touched here,
  out of scope.

All three now require `Depends(get_current_user)`; `organization_id`/`tenant_id` derived from
`current_user.organization_id`, never client-supplied; `is_super_admin` derived from
`current_user.roles` (checking specifically `SuperAdmin`, matching the endpoint's own stated
scope). `graph_evolution.py`'s edge dict is now keyed by
`f"{organization_id}:{source_id}->{relation_type}->{target_id}"`, and every read/write path
filters to the calling org's own edges.

All three test files extended with real authentication and real cross-tenant isolation
assertions -- `test_graph_evolution.py`'s new Test 4 specifically proves Org A's `traverse`
never returns Org B's edge weight even when `source_id`/`target_id` collide, and that Org A's
decay sweep never mutates Org B's edges, the exact scenario the finding named. One real
regression the change caused was caught by the full suite and fixed:
`test_frontend_api_contract.py`'s Knowledge Graph contract check was calling the now-protected
`/graph-evolution/traverse` route unauthenticated. Master suite: **89/89 passing**. See
`docs/phase83_unauthenticated_endpoint_security_fixes.md`.

### Explicitly deferred, not dropped — still open findings from the same sweep
The user chose to fix only the 3 highest-severity findings this turn. Still open, awaiting an
explicit future request:
- 6 lower-risk unauthenticated-but-stateless routers (`model_router.py`, `observability.py`,
  `security_guard.py`, `rate_limiter.py`, `prompts.py`, `evaluations.py`).
- A Sidebar dead-button frontend bug.
- `ContextSearchTool`'s mock-data fallback trap.
- A fabricated RBAC `user_id` somewhere in the auth path.
- Two orphaned SQLAlchemy models (`ModelConfiguration`, `AnalyticsMetric`) with no real
  read/write path.
- An empty `backend/app/crud/` package.
- Whether `graph_evolution.py`'s parallel in-memory graph subsystem should be retired in favor
  of the real Phase 59 knowledge graph -- a real architecture question, bigger than "fix the
  unauthenticated endpoint."

## 9 · Closing the Remaining Sweep Findings — Phase 84

The first of the six items Phase 83 explicitly deferred: `model_router.py`,
`observability.py`, `security_guard.py`, `rate_limiter.py`, `prompts.py`, `evaluations.py` --
16 endpoints total across the 6 routers, all completely unauthenticated. Read all 6 files and
their backing engines in full before designing a fix: unlike Phase 83's three, **none of these
six have any `organization_id`/tenant concept anywhere** -- each backs a process-global piece
of internal platform infrastructure (model routing config, OTel span buffer, prompt-injection/
PII scanner, token-bucket rate limiter, prompt version registry, agent-evaluation scorer) that
every organization's traffic already shares by design. Confirmed via grep: zero frontend
callers for any of the six, consistent with Phase 83's `memory_lifecycle.py` finding -- these
are internal/engineering-facing endpoints only. So the fix is narrower than Phase 83's: just
`Depends(get_current_user)` added to all 16 endpoints, no `organization_id`/privilege-field
removal needed since none of these ever accepted one.

All 6 dedicated test suites and `test_frontend_api_contract.py` updated to authenticate and to
assert an unauthenticated request is correctly rejected (matching Phase 83's test pattern), all
passing standalone. Master suite: **89/89 passing**. One background run of the full suite
stalled for 35+ minutes with zero log progress at Phase 77's real GitHub API test -- the same
class of non-reproducible environment flakiness documented earlier in this engagement (Phases
59-61, and the Phase 75/76 window); killed and re-run cleanly, confirming non-regression. See
`docs/phase84_remaining_unauthenticated_routers.md`.

**Still open from the same sweep**, unrelated to authentication and explicitly deferred: the
Sidebar dead-button frontend bug, `ContextSearchTool`'s mock-fallback trap, a fabricated RBAC
`user_id`, two orphaned models, and the empty `crud/` package.

## 10 · Closing the Remaining Sweep Findings — Phase 85

Three of the five remaining sweep findings, closed on "continue":

- **Sidebar dead-button bug**: `frontend/components/Sidebar.tsx` rendered every nav item as a
  real `<Link>` except the one whose `path === "/"` ("Executive Overview"), which instead
  called `onTabChange`/`setActiveTab` -- props only `app/page.tsx` (the home dashboard, which
  has its own real in-page tab UI) actually passes. Verified via grep: **20 of ~22 pages**
  render `<Sidebar>` without those props, so clicking "Executive Overview" from any of them did
  nothing. `github/page.tsx` was worse -- it passed an explicit no-op `onTabChange={() => {}}`.
  Fixed: the button branch is now taken only when the caller actually supplied a tab-state
  handler; every other page falls through to a real `<Link href="/">`. The no-op prop removed
  from `github/page.tsx`.
- **`ContextSearchTool` mock-fallback trap**: its `execute` fabricated a fake `"status":
  "success"` result with a `mock-chunk-1` / `0.88` score whenever `session` was `None` --
  indistinguishable from a real result. Verified this was the sole exception to this codebase's
  own convention (every other tool with the same optional-session signature raises
  `ValueError`), and that the only real caller (`ToolService`) always supplies a real session,
  so this was unreachable today but a real landmine for tomorrow. Fixed to raise the same
  `ValueError` every other tool already raises.
- **Fabricated RBAC `user_id`**: `ToolExecutor.check_permission` built its PDP authorization
  request with `user_id=str(uuid.uuid4())` -- a fresh random UUID on every call -- even though
  the real caller's `user_id` was already threaded one hop away (`POST /tools/execute` already
  passes `current_user.id` into `execute_tool`, just never one hop further into
  `check_permission`). Verified the PDP's actual authorization decision never read this field
  (role/risk-based only), so this wasn't a live bypass, but it was exactly the "required field
  filled with noise instead of real data" pattern this engagement exists to close. Fixed:
  `ToolCallAuthorizationRequest.user_id` is now `Optional[str] = None` (representable as
  "genuinely unknown" for the two real callers -- workflow/agent-step execution -- that have no
  single acting user in the current data model), and `check_permission` now threads the real
  `user_id` through when one exists. `test_tool_registry.py` extended with a new test that
  captures the live PDP request via a patched `evaluate_tool_call` and asserts it carries the
  real authenticated caller's real database user id.

Master suite: **89/89 passing**. See
`docs/phase85_dead_button_mock_trap_fabricated_user_id.md`.

**Still open, deliberately deferred**: `ModelConfiguration`/`AnalyticsMetric`, two orphaned
SQLAlchemy models with real relationships but zero real read/write path anywhere in the app,
and the empty `backend/app/crud/` package. Both cause zero incorrect behavior today (nothing
reads or writes them, so there's no fabrication or security risk) -- removing an ORM model
touches the DB schema/migration history, a more deliberate, separate decision than a
"continue" turn should make unprompted.
