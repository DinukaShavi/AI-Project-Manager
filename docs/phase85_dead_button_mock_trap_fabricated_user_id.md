# Phase 85 Plan: Sidebar Dead Button, ContextSearchTool Mock Trap, Fabricated RBAC user_id

**Status:** Implemented and verified. Three of the five remaining items from the original full-project
sweep (Phase 83/84 closed the six unauthenticated-router findings). The other two —
`ModelConfiguration`/`AnalyticsMetric` orphaned models and the empty `backend/app/crud/`
package — are explicitly deferred here, not fixed: both cause zero incorrect behavior (nothing
in the app reads or writes them, so there's no fabrication or security risk), and removing an
ORM model touches the DB schema/migration history, a more deliberate, separate decision than a
"continue" turn should make unprompted.

## 1. Sidebar dead-button bug (frontend)

`frontend/components/Sidebar.tsx`'s `navItems` renders every item as a real `<Link
href={item.path}>` except when `item.path === "/"` (only the "Executive Overview" item),
which instead renders a `<button onClick={() => changeTab(item.id)}>` that only calls
`onTabChange`/`setActiveTab` if the parent passed them. Verified via grep: **20 of the ~22
pages that render `<Sidebar>`** (`calendar`, `workflows`, `tasks`, `analytics`, `slack`,
`jira`, `settings`, `agent-dashboard`, etc.) pass neither prop — only `frontend/app/page.tsx`
(the home dashboard itself) passes `setActiveTab`, because it has its own real, working
in-page tab-switching UI for `overview`/`workflows`/`tasks`/`context` sections. So on every
other page, clicking "Executive Overview" in the sidebar silently does nothing — a real dead
button, not a cosmetic issue, present on the majority of the app's pages. Worse:
`frontend/app/github/page.tsx` renders `<Sidebar activeTab="github" onTabChange={() => {}}
/>` — an explicit no-op that actively swallows the click rather than merely omitting a handler.

**Fix:** only take the tab-switching (button) branch for the `path === "/"` item when the
caller actually supplied `onTabChange` or `setActiveTab` (i.e. only on the home page, whose
existing working UI is untouched). Every other page falls through to a real `<Link href="/">`,
navigating home for real. Remove `github/page.tsx`'s no-op `onTabChange={() => {}}` prop so it
also falls into the same real-navigation path instead of continuing to swallow the click.

## 2. ContextSearchTool mock-fallback trap (backend)

`backend/app/tools/context_tools.py`'s `ContextSearchTool.execute` returns a **fabricated**
`"status": "success"` result with a fake `mock-chunk-1` / `0.88` score whenever `session` is
`None` — indistinguishable from a real result to any caller. Verified this is the sole
exception to this codebase's own convention: every other tool with the same `session:
Optional[AsyncSession] = None` signature (`GitHubCreateIssueTool` via `_get_github_connector`,
`SlackPostMessageTool`, `SlackReplyInThreadTool`) treats a missing session as a real error --
`raise ValueError("Database session required...")`, surfaced as `status: "error"`, never
fabricated data. Also verified the only real caller, `ToolService.execute_tool`
(`backend/app/services/tool.py:31`), is constructed with a required (non-Optional)
`AsyncSession` and always passes `session=self.session` -- so this mock branch is genuinely
unreachable via any real path today, but it's still a landmine: any future direct call (or a
refactor that makes the session genuinely optional somewhere) would silently return fabricated
"success" data instead of a real error, exactly the failure mode this whole engagement has
been closing everywhere else.

**Fix:** replace the mock fallback with the same pattern every other tool already uses --
`raise ValueError("Database session required to execute a real context search.")`.

## 3. Fabricated RBAC user_id (backend)

`backend/app/tools/executor.py:49` -- `ToolExecutor.check_permission` builds a
`ToolCallAuthorizationRequest` with `user_id=str(uuid.uuid4())`, a **freshly fabricated random
UUID on every single call**, even though the real caller's `user_id` is already available:
`execute_tool` (the only caller of `check_permission`) receives a real `user_id:
Optional[uuid.UUID]` parameter, and `POST /api/v1/tools/execute` already threads
`current_user.id` into it (`backend/app/api/v1/tools.py:49`) -- it just never reaches
`check_permission`, one hop short. Verified `PolicyDecisionPoint.evaluate_tool_call` never
actually reads `request.user_id` in its authorization decision today (role/risk-based only),
so this isn't a live authorization bypass -- but it's exactly the "required field filled with
noise instead of real data" pattern this engagement's own discipline exists to close, and it
would silently corrupt any future use of that field (e.g. per-user audit/rate-limit logic
added later inside the PDP). Two other real callers of `execute_tool`
(`app/workflows/executor.py`, `app/services/intelligence_engine.py`) never pass a `user_id` at
all -- a workflow DAG step execution genuinely has no single "acting user" in the current data
model, so there is no real value to fabricate there either.

**Fix:** `ToolCallAuthorizationRequest.user_id` becomes `Optional[str] = None` (representable
as "genuinely unknown", not forced to be a lie). `check_permission` gains a `user_id:
Optional[uuid.UUID] = None` parameter and passes `str(user_id) if user_id else None` instead
of a fabricated UUID. `execute_tool`'s call site passes its own real `user_id` through. When a
real caller supplies one (the HTTP endpoint), the PDP request now carries the real value; when
none exists (workflow/agent-step paths), it stays honestly `None`.

## Files expected to change

- `frontend/components/Sidebar.tsx` -- conditional real navigation for the home-tab item.
- `frontend/app/github/page.tsx` -- remove the no-op `onTabChange={() => {}}`.
- `backend/app/tools/context_tools.py` -- replace fabricated mock fallback with a real error.
- `backend/app/core/rbac_pdp.py` -- `user_id: Optional[str] = None`.
- `backend/app/tools/executor.py` -- thread the real `user_id` through `check_permission`.
- `backend/tests/test_tool_registry.py` -- extend to assert the real `user_id` reaches the PDP
  request (not a random UUID) for an authenticated `POST /tools/execute` call.

## Test plan

- `ContextSearchTool.execute(params, session=None)` raises `ValueError`, matching every other
  tool's convention, instead of returning fabricated success data.
- `ToolExecutor.check_permission` / `execute_tool`: when a real `user_id` is supplied, the
  `ToolCallAuthorizationRequest` the PDP receives carries that exact value, not a random UUID;
  when none is supplied, it's `None`, not fabricated.
- Existing `test_rbac_pdp.py` and `test_tool_registry.py` suites keep passing.
- Master suite stays green (89/89, no new suite files).
- Frontend fix verified by reading the rendered logic path (no frontend test harness exists in
  this codebase for component-level assertions, consistent with every prior frontend fix in
  this engagement).

## Result

All three fixed. `test_tool_registry.py` extended with a new Test 8: patches
`PolicyDecisionPoint.evaluate_tool_call` to capture the `ToolCallAuthorizationRequest` a real
authenticated `POST /tools/execute` call produces, and asserts its `user_id` equals the real
caller's real database user id -- not a random UUID. `test_rbac_pdp.py` unaffected (constructs
`ToolCallAuthorizationRequest` directly with a real string already). Master suite: **89/89
passing**.
