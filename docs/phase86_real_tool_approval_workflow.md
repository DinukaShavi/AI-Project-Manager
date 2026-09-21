# Phase 86 Plan: Make the Human-in-the-Loop Tool Approval Gate Real (P0)

**Status:** Implementing. Surfaced by a requirements audit against
`docs/implementation_roadmap.md` §1 Milestone 12, whose Definition of Done states:
*"Tools validate inputs, token injection handles credentials, and mutating tools wait for
approval."* They do not wait in any enforceable sense today.

## The defect

`backend/app/tools/executor.py:112`

```python
if self.requires_approval(tool_name) and not approval_token:
    approval_id = str(uuid.uuid4())     # generated, returned to the caller... and discarded
    return {"status": "WAITING_APPROVAL", "approval_id": approval_id, ...}
```

The `approval_id` is **never persisted**, and `approval_token` is **never validated against
anything**. The guard is a plain truthiness check, so any caller who receives
`WAITING_APPROVAL` can immediately retry the identical call with `approval_token: "x"` — any
non-empty string — and the high-risk tool executes for real. `backend/tests/test_tool_registry.py`
Test 7 demonstrates this unintentionally by passing the literal string `"approved-by-test"`.

Affected tools are exactly the ones the architecture spec designates as most dangerous
(`ToolExecutor.HIGH_RISK_SIDE_EFFECT_TOOLS`): `merge_pull_request`, `deploy_release`,
`delete_repository`, `jira_delete_issue`, `slack_broadcast_all`.

This is simultaneously:
- a **requirements failure** (M12 DoD unmet; `POST /api/v1/tools/approve/{id}`, a specified
  M12 endpoint, does not exist at all), and
- a **real privilege-escalation path** — a Developer-role user who is denied nothing by the
  PDP for `merge_pull_request` can self-approve their own high-risk call, defeating the
  "Approval Queuer" component that `enterprise_ai_architecture_spec.md` §5 defines as
  *"Suspend executions and publishes approval requests to user notification channels."*

## Design

Approval becomes a real, persisted, tenant-scoped, single-use grant — not a string.

**New table `tool_approvals`** (`app/models/agent.py` + Alembic migration):
`organization_id`, `requested_by_user_id`, `approved_by_user_id`, `tool_name`,
`tool_parameters`, `parameters_fingerprint`, `status`
(`pending|approved|rejected|consumed`), `approval_token_hash`, `expires_at`, `consumed_at`.

Four properties make the grant non-forgeable, each closing a specific attack:

1. **The token is a real secret, stored hashed.** `secrets.token_urlsafe(32)` is issued once
   at approval time; only its SHA-256 lands in the database. Guessing is infeasible and a
   database read never yields a usable token.
2. **The grant is bound to the exact call.** `parameters_fingerprint` is a SHA-256 over the
   canonical (sorted-key) JSON of the parameters. Approving "merge PR #42 on acme/web" cannot
   be replayed to merge a different PR or a different repository.
3. **The grant is single-use.** Validation flips `pending/approved → consumed` in the same
   transaction, so a captured token cannot be replayed.
4. **The grant is tenant-scoped and expiring.** Validation requires a matching
   `organization_id` (derived from the JWT, never client-supplied) and
   `expires_at > now` (default 30 minutes).

**Approver authority follows the spec's own matrix**, not an invented rule.
`enterprise_ai_architecture_spec.md` §5 assigns an explicit approval policy per tool, which
becomes `TOOL_APPROVER_ROLES` in `app/core/rbac_pdp.py`:

| Tool | Spec's stated policy | Roles allowed to approve |
| --- | --- | --- |
| `delete_repository` | "Requires Super Admin validation" | `SuperAdmin` |
| `deploy_release` | "PM validation required" | `SuperAdmin`, `OrgAdmin`, `ProjectManager` |
| `merge_pull_request` | "PM approval required if CI fails" | `SuperAdmin`, `OrgAdmin`, `ProjectManager` |
| others high-risk (`jira_delete_issue`, `slack_broadcast_all`) | not in the spec table | `SuperAdmin`, `OrgAdmin` (default) |

A **requester may not approve their own request** (four-eyes). This is the entire point of the
control: without it a Developer still self-authorizes, just with extra steps.

**Fail closed.** If a high-risk tool call arrives with no database session, the approval cannot
be verified, so the call is **denied** rather than allowed. `intelligence_engine.py` currently
calls `execute_tool` without passing its own `self.db`; that is corrected so real agent plans
keep working through the real approval path instead of tripping the fail-closed branch.

**Notification.** Creating a pending approval broadcasts
`{"event": "tool_approval_requested", ...}` over the existing org WebSocket via
`get_connection_manager().broadcast_to_organization(...)` — the same mechanism Phase 66 uses,
satisfying M12's "WebSocket Events: Request tool approval alert" and the spec's "Approval
Queuer ... publishes approval requests to user notification channels", without inventing a
second real-time channel.

## API (Milestone 12)

- `POST /api/v1/tools/approve/{approval_id}` — **the endpoint M12 specifies and that did not
  exist.** Returns the one-time `approval_token`. Enforces approver role + four-eyes + tenancy.
- `POST /api/v1/tools/reject/{approval_id}` — the natural counterpart.
- `GET /api/v1/tools/approvals` — pending queue, so M12's "UI widgets to review and approve
  pending tool calls" has real data to render.

## Files expected to change

- `backend/app/models/agent.py` — `ToolApproval` model.
- `backend/alembic/versions/<new>_add_tool_approvals_table.py` — migration (head `dec7fc9bcf57`).
- `backend/app/core/rbac_pdp.py` — `TOOL_APPROVER_ROLES`, `DEFAULT_APPROVER_ROLES`.
- `backend/app/services/tool_approval.py` — new service (create/approve/reject/validate/list).
- `backend/app/tools/executor.py` — persist pending, validate+consume, fail closed.
- `backend/app/api/v1/tools.py` — the three endpoints above.
- `backend/app/services/intelligence_engine.py` — pass `db` through to `execute_tool`.
- `backend/tests/test_tool_approval_workflow.py` — new suite, registered in `run_all_tests.py`.
- `backend/tests/test_tool_registry.py` — Test 7 currently *depends on the bypass*; it must be
  rewritten to prove the bypass is gone and to drive the real approval flow.

## Test plan

The suite must prove the hole is actually closed, not merely that a happy path works:

1. A forged/arbitrary `approval_token` ("approved-by-test", a random UUID) is **rejected**.
2. A high-risk call with no token creates a real `pending` row and returns its real id.
3. A Developer **cannot** approve (403); a ProjectManager **can** approve `deploy_release`;
   only a SuperAdmin can approve `delete_repository`.
4. The requester **cannot** approve their own request (four-eyes), even as SuperAdmin.
5. An approved token executes the tool exactly once; **replaying** it is rejected (consumed).
6. A token approved for one parameter set is **rejected** when the parameters are changed.
7. An approval issued in Org A is **rejected** for the identical call made from Org B.
8. An expired approval is rejected.
9. Low-risk tools are unaffected (no approval required, no behavior change).
10. Master suite stays green.
