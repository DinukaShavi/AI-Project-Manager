# Phase 80 Plan: Ground the Monte Carlo Forecast in Real Data

**Status:** Implemented and verified. 4/4 feature checks passing standalone (real Jira velocity
+ real remaining points grounding, honest default fallback with no real data, explicit caller
overrides always honored and correctly labeled, no-db path unaffected); 89/89 master suite
passing, no pre-existing test regressions. First of a new 3-item grounded plan (Monte Carlo real-data inputs →
GitHub/Jira `ASSIGNED_TO` edge resolution → reranking extended to more callers), surfaced by
investigating the Analytics category (65, the lowest remaining audit score) directly rather
than guessing at what to fix.

## What's already there, re-verified (investigation, not assumption)

Confirmed via direct code reading, not inference:

- `ProjectIntelligenceEngine.process_goal` Stage 5 (`intelligence_engine.py:121-127`) calls
  `MonteCarloPredictor.run_simulation(historical_velocities=historical_velocities or [6.0, 7.0,
  5.5, 8.0], remaining_points=remaining_points)` -- when the caller (the `POST
  /planning/intelligence` request body) doesn't supply real values, which is the normal case,
  these hardcoded numbers are used.
- `IntelligenceGoalRequest.remaining_points` (`api/v1/planning.py:97`) already defaults to
  `Optional[float] = 25.0`, and the router passes `payload.remaining_points or 25.0`
  (`planning.py:115`) -- meaning `process_goal` never actually sees `None` for
  `remaining_points` today; the router pre-resolves it before the "was this a real override or
  not" distinction can be made downstream.
- Two real data sources already exist and are completely disconnected from this stage:
  `IntegrationService.get_jira_velocity_for_project` (Phase 72) returns real
  `sprint_velocity_history` (completed points per real closed sprint), and `ProjectTask` rows
  (Phase 76 sync) carry real `story_points`/`status` that can be summed for real remaining
  work. Neither is queried anywhere near `process_goal`.
- `frontend/app/analytics/page.tsx` never calls `/planning/intelligence` at all -- the
  synthetic defaults are entirely backend-side and unreached by the one page that might
  otherwise expose them; this phase's fix has no frontend surface to update.

## Design

- **`IntelligenceGoalRequest.remaining_points`** becomes `Optional[float] = None` (was `25.0`);
  the router passes `payload.remaining_points` straight through, unresolved -- the "no override
  supplied" case is now representable end-to-end instead of being pre-decided at the API layer.
- **`ProjectIntelligenceEngine.process_goal`**'s `remaining_points` parameter becomes
  `Optional[float] = None` to match.
- **New `_resolve_forecast_inputs(organization_id, project_id, historical_velocities,
  remaining_points)`**: for whichever of the two inputs the caller left unset, and only when a
  real `self.db` session and `project_id` are available (mirrors the exact guard Stage 1's
  graph loading and Phase 69's real agent execution already use):
  - Real velocities: `get_jira_velocity_for_project`'s `sprint_velocity_history`, extracting
    each closed sprint's real `completed` points.
  - Real remaining points: `SUM(ProjectTask.story_points) WHERE status != 'done'`, real,
    tenant+project-scoped.
  - Best-effort (`try/except`) -- a Jira-not-connected `ValueError`/`LookupError` or any other
    failure falls through silently to the next tier, never crashes `process_goal`.
  - Falls back to the original hardcoded example numbers only when neither the caller nor real
    project data supplies a value -- same three-tier honesty discipline (real → real fallback →
    honest labeled default) established throughout this engagement.
- **Transparency, not silent substitution**: `process_goal`'s return dict gains
  `forecast_data_source: {"velocities": "caller"|"real"|"default", "remaining_points":
  "caller"|"real"|"default"}` alongside the existing `monte_carlo_predictive` key, so a caller
  (or a future UI) can tell whether the forecast is grounded in an explicit override, this
  project's real history, or the documented example numbers -- never presented as equally
  authoritative when they're not.

## Explicitly out of scope for this turn

- Any change to `MonteCarloPredictor` itself -- the simulation math is untouched; only its
  inputs' provenance changes.
- Surfacing `forecast_data_source` in the frontend -- `analytics/page.tsx` doesn't call this
  endpoint today (confirmed above); adding that call is a separate, real frontend feature, not
  bundled into this backend-grounding fix.

## Files expected to change

- `backend/app/api/v1/planning.py` -- `IntelligenceGoalRequest.remaining_points` default,
  router pass-through.
- `backend/app/services/intelligence_engine.py` -- `remaining_points` signature,
  `_resolve_forecast_inputs`, Stage 5 wiring, `forecast_data_source` in the return dict.
- `backend/tests/test_real_monte_carlo_forecast.py` (new).
- `backend/tests/run_all_tests.py` -- register Phase 80.

## Test plan

- A project with real closed-sprint Jira velocity data and real non-done `ProjectTask` story
  points, called with no explicit overrides: the forecast uses the real values (verified
  against a hand-computed expectation), `forecast_data_source` reports `"real"` for both.
- A project with no real data available (no Jira connection, no tasks): falls back to the
  exact original hardcoded defaults, `forecast_data_source` reports `"default"` for both --
  proves the fallback is unchanged in the no-real-data case, not just present.
- An explicit caller-supplied override for either field is honored as-is, never overwritten by
  real-data lookup -- `forecast_data_source` reports the overridden field came from the caller,
  not "real" (a caller-supplied value isn't this project's real history either).
- The no-db unit-test path (`ProjectIntelligenceEngine()` with no session) is unaffected --
  falls straight to the honest defaults, matching Phase 69's preserved no-db contract.
- Master suite stays green (89/89 expected).
