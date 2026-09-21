# Phase 79 Plan: Calendar Faster Poll Interval

**Status:** Implemented and verified. `test_calendar_poller.py`'s Test 1 asserted the specific
historical `900` value; updated to assert a real, positive, no-slower-than-900s cadence instead
of a value this phase deliberately changed -- all 10 of that suite's checks pass, 88/88 master
suite (unchanged count, no new suite needed for a one-line config change). Third and final part
of the depth phase (broaden real actions → real
search reranking → **Calendar real-time**), targeting Real-time events (75), Calendar being
the one integration still poll-only.

## What changed from the original plan, and why

The original framing ("wire Calendar's existing push-notification signature verification to
trigger a real sync") turned out to understate the real scope: nothing in this codebase ever
registers a Google push-notification Watch channel in the first place (`events.watch` is never
called), so Google has no channel to notify through; and even a received notification carries
only an opaque `channel_id`/`resource_id`, with no stored mapping back to which organization's
project(s) to sync (`sync_calendar_events` syncs one shared org-level "primary" calendar per
project on demand, not a fixed one-calendar-per-project relationship) -- plus watch channels
expire (~7 days) and need real renewal. Building this properly is a materially larger phase,
closer in size to Phase 55's OAuth site resolution than a quick wiring pass. Investigated,
explained, and asked (via AskUserQuestion) rather than either quietly scoping it down or
building more than agreed -- **decision: shorten the poll interval instead**, which delivers
most of the practical benefit (Calendar data staleness drops from up to 15 minutes to up to 2)
with a one-line config change and no new integration surface.

## What's already there, re-verified

`_calendar_poller_loop` (`app/workers/event_worker.py:104-143`) is correctness-safe at any
interval already, requiring no changes: the Redis-backed distributed lock
(`DistributedLockManager`, `ttl_seconds=300`) is acquired once per cycle and explicitly
released in a `finally` block immediately after that cycle completes -- not held for the full
TTL -- so a shorter `CALENDAR_POLL_INTERVAL_SECONDS` cannot cause overlapping cycles between
healthy instances; the TTL only matters as a crash-failover safety net (an instance that
crashes mid-cycle without releasing), which stays a rare edge case regardless of the poll
cadence.

## Design

- `settings.CALENDAR_POLL_INTERVAL_SECONDS` default changed from `900` (15 min, the original
  documented Milestone 10 value) to `120` (2 min) -- a real, meaningful reduction (7.5x more
  frequent) without being excessive against Google Calendar API quota for orgs with no actual
  changes between cycles.
- Lock TTL (`300`s) left unchanged -- it already only matters for crash-failover, not
  steady-state cadence, and a wider TTL than the new interval doesn't reintroduce any overlap
  risk given the explicit release-in-`finally` pattern already in place.

## Explicitly out of scope for this turn

- Real Google Calendar Watch-channel push notifications -- the materially larger alternative
  investigated and declined this turn; left as a real, well-scoped future option if ever
  wanted, not pursued speculatively.

## Files expected to change

- `backend/app/core/config.py` -- `CALENDAR_POLL_INTERVAL_SECONDS` default.

## Test plan

No new test suite -- this is a single config default change to an already-tested, already-
correctness-verified poller loop (`test_calendar_meet_links_availability.py` and others already
exercise `sync_calendar_events`/`run_calendar_poll_sync` directly, independent of the sleep
interval, which isn't itself exercised by any test's timing). Verification here is: master
suite stays green (88/88, unchanged suite count -- no new test file), confirming the config
change didn't regress anything that depends on the poller's structure.
