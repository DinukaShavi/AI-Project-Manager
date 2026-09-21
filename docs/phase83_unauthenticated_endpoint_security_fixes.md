# Phase 83: Fix 3 Unauthenticated Endpoints Found by a Full-Project Security Sweep

**Status:** Implemented and verified. Surfaced by a fresh, systematic sweep (four parallel
scans across mock-data, security, frontend, and test-coverage) run at the user's request
after the punch list and both depth phases were already closed -- not something any single
phase's narrow scope would have caught, since nothing pointed at these three specific files
before. All three routers now require real authentication and derive every tenant-identifying
or privilege-claiming field server-side. `test_memory_lifecycle.py`, `test_tenant_isolation.py`,
and `test_graph_evolution.py` all extended with real auth + real cross-tenant isolation
assertions and pass standalone. One real regression this change caused was caught by the full
suite and fixed: `test_frontend_api_contract.py`'s Knowledge Graph contract check was calling
`/graph-evolution/traverse/node-1` with no auth headers, which now correctly 401s -- fixed by
authenticating that call with the same org/headers the test already creates for the Cost
Monitoring check just above it. Master regression suite: **89/89 passing** (two unrelated,
pre-existing flaky failures on the first run -- Phase 15's per-user rate-limit dimensioning
test and the same frontend-contract file before the fix above -- both confirmed non-regressions
by re-running standalone; the Phase 15 flake is the same class of environment flakiness
documented earlier in this engagement at Phases 59-61, unrelated to any Phase 83 code).

## What the sweep found, re-verified by reading every line of all three files and their
## backing engines before designing a fix

- **`backend/app/api/v1/memory_lifecycle.py`** -- 3 endpoints (`/compress`, `/gc`,
  `/rebuild-index`), zero `Depends(get_current_user)` anywhere in the file,
  `organization_id` a plain client-supplied body field. Investigated the backing
  `MemoryLifecycleEngine` (`app/services/memory_lifecycle.py`) fully: it is a **stateless,
  process-global, in-memory-only** utility -- `compress_conversation_history` and
  `run_garbage_collection` operate entirely on `messages`/`memory_records` the caller supplies
  directly in the request body, never reading real `ContextChunk`/`ContextEmbedding` rows;
  `organization_id` is only ever used as a label on the returned result and on in-memory
  `ArchiveLogRecord`s appended to a Python list on the singleton. Confirmed via grep this
  router has **zero frontend callers** (`frontend/`) and is reachable only through direct API
  calls. Real risk: anonymous, unbounded calls (resource use on the singleton's growing lists)
  and a generally bad security posture (no login required at all), not a real per-tenant data
  leak -- there is no real per-tenant data here to leak. Still a real gap to close: nothing in
  this application should be callable without authentication.
- **`backend/app/api/v1/tenant_isolation.py`** -- 3 endpoints, zero auth. The two namespacing
  endpoints (`/partition-keys`, `/validate-vector-query`) are also stateless string-formatting
  utilities over `app/core/tenant_isolation.py`'s `TenantIsolationEngine`. The third,
  `/audit-access`, is the real, serious finding: `audit_cross_tenant_access`'s `is_super_admin`
  is a **client-supplied boolean in the request body**, passed straight into
  `TenantIsolationEngine.audit_cross_tenant_access`, which grants cross-tenant access whenever
  it's `true` -- a caller can simply claim `is_super_admin: true` in the JSON body and get
  `"allowed": true"` for any cross-tenant "audit" decision, on the one endpoint whose entire
  purpose is enforcing that boundary.
- **`backend/app/api/v1/graph_evolution.py`** -- 4 endpoints, zero auth. Investigated the
  backing `KnowledgeGraphEvolutionEngine` (`app/services/graph_evolution.py`) fully: unlike the
  other two, this one **does hold real, request-spanning shared state** --
  `self.edges: Dict[str, GraphEdgeRecord]` on the process-global singleton, keyed only by
  `f"{source_id}->{relation_type}->{target_id}"`, with **no `organization_id` field anywhere
  on `GraphEdgeRecord`**. `link_entities`/`infer_implicit_edges` write into this shared dict;
  `traverse_graph`/`apply_decay_sweep` read/mutate across the *entire* dict regardless of who
  created which edge. Confirmed via grep this engine has **zero callers anywhere else in the
  codebase** -- it is a separate, never-wired-in parallel graph implementation, entirely
  disconnected from the real, DB-backed, tenant-scoped `ProjectKnowledgeGraph`/
  `KnowledgeGraphEdge` (Phase 59). This is the one genuine cross-tenant read/write risk of the
  three: if `source_id`/`target_id` values ever collide across organizations (plausible --
  e.g. a Jira key format like "PROJ-123" is common across many real orgs), one org's traversal
  can read edges another org created, and a decay sweep mutates weights across every org's
  edges at once.

## Design

All three get the same treatment, matching this codebase's standing pattern everywhere else:
`Depends(get_current_user)` added to every endpoint; any tenant-identifying field
(`organization_id`/`tenant_id`) removed from the request body and derived from
`current_user.organization_id` instead; any privilege claim (`is_super_admin`) removed from
the request body and derived from `current_user.roles` instead.

- **`memory_lifecycle.py`**: `Depends(get_current_user)` added; `organization_id` dropped from
  all three request models, `current_user.organization_id` passed to the engine instead.
- **`tenant_isolation.py`**: `Depends(get_current_user)` added; `tenant_id`/`source_tenant_id`
  dropped from all three request models, derived from `current_user.organization_id`.
  `is_super_admin` dropped from `AuditAccessRequest` entirely -- computed server-side by
  checking `UserRole.SUPER_ADMIN.value in {r.name for r in current_user.roles}` (specifically
  `SuperAdmin`, not the broader `ADMIN_ROLES`, matching `audit_cross_tenant_access`'s own
  docstring: cross-tenant access is a super-admin-only concern, not an org-admin one, since an
  OrgAdmin has no legitimate reason to cross tenant boundaries either).
- **`graph_evolution.py`**: `Depends(get_current_user)` added. `GraphEdgeRecord` gains a real
  `organization_id: str` field; `KnowledgeGraphEvolutionEngine`'s edge dict key becomes
  `f"{organization_id}:{source_id}->{relation_type}->{target_id}"` (composite, org-scoped);
  `link_entities`/`infer_implicit_edges` take `organization_id`;
  `traverse_graph`/`apply_decay_sweep` filter to only the calling org's own edges. `source_id`/
  `target_id`/`start_node_id` stay caller-supplied (they identify entities *within* an org, not
  the org itself) -- only the org boundary changes from ambient/shared to real and enforced.

## Explicitly out of scope for this turn

- Whether `graph_evolution.py`'s entire parallel in-memory graph subsystem should be retired
  in favor of the real Phase 59 `ProjectKnowledgeGraph`/`KnowledgeGraphEdge` -- a real
  architecture question, but a separate, bigger one than "fix the unauthenticated endpoint,"
  which is what was asked.
- The 6 lower-risk unauthenticated-but-stateless routers found in the same sweep
  (`model_router.py`, `observability.py`, `security_guard.py`, `rate_limiter.py`, `prompts.py`,
  `evaluations.py`) -- explicitly deferred, not silently dropped; the user chose to fix only
  the 3 highest-severity findings this turn.
- The Sidebar dead-button frontend bug, the `ContextSearchTool` mock-fallback trap, the
  fabricated RBAC `user_id`, and the two orphaned models -- all found in the same sweep,
  all explicitly deferred by the same scoping choice.

## Files expected to change

- `backend/app/api/v1/memory_lifecycle.py`
- `backend/app/api/v1/tenant_isolation.py`
- `backend/app/api/v1/graph_evolution.py`
- `backend/app/services/graph_evolution.py` -- `organization_id` field + org-scoped edge keys.
- `backend/tests/test_memory_lifecycle.py`, `backend/tests/test_tenant_isolation.py`,
  `backend/tests/test_graph_evolution.py` -- update to authenticate and stop supplying the
  now-removed request fields; extend with real cross-tenant isolation assertions (the class of
  test every other real endpoint in this codebase already has).
- `backend/tests/test_frontend_api_contract.py` -- caught by the full suite: its Knowledge
  Graph contract check called `/graph-evolution/traverse/node-1` unauthenticated, which now
  correctly 401s. Fixed to reuse the org/headers already created for the Cost Monitoring check.

## Test plan

- All three routers: unauthenticated request -> 401/403, not silently degraded behavior.
- `tenant_isolation.py`: a non-super-admin caller cannot get `allowed: true` for a
  cross-tenant audit even by claiming `is_super_admin` in the request body (the field no
  longer exists in the request schema, so this is structurally impossible, not just checked);
  a real SuperAdmin caller can.
- `graph_evolution.py`: Org A's `traverse_graph` does not return Org B's edges even when
  `source_id`/`target_id` collide between the two orgs (the exact scenario the finding named);
  `apply_decay_sweep` only mutates the calling org's own edges.
- Existing suites for all three (`test_memory_lifecycle.py`, `test_tenant_isolation.py`,
  `test_graph_evolution.py`) updated and passing.
- Master suite stays green (89/89, no new suite files -- extends existing ones).
