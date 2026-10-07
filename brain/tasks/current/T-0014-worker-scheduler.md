# T-0014 — Worker + scheduler: split the agent into api / worker / scheduler

| Field | Value |
|---|---|
| Status | `in progress` (2026-10-07): step 1 done |
| Phase | 9 — agent workflow ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)): "a real worker and scheduler" |
| Architecture | no change (no ACR): implements ARCHITECTURE §6.2 (intake claim + lease recovery), §6.5 (skip-if-active, maximum queued age), §6.6 (scheduled identity), §7.3 (scheduler), §3 containers `argus-api` / `argus-worker` / `argus-scheduler` |
| Branch | `task/T-0014-worker-scheduler` |
| Owner | `juanbetancurm` (+ agent) |
| Needs the VM lease | step 5 only (vm-095) |

## Goal (plain language)

Today one container does everything: it answers the API, receives alerts, and runs investigations in a background
thread. If an investigation crashes the container, the API goes down with it, and on restart **every** run marked
"running" is taken back, which would be wrong as soon as two workers exist. T-0014 splits Argus into three programs
from the same image: the **api** (accepts requests, never investigates), the **worker** (claims queued incidents
one by one, holds a renewable claim on each, and resumes an interrupted run from its LangGraph checkpoint), and the
**scheduler** (submits periodic health investigations from a file; it never runs detectors, the model or the graph).

## Decisions (proposed, to confirm at the start)

- **The scheduler writes the intake row in-process** (the application use case, as the HTTP handler does), not over
  internal HTTP: §3 allows "argus-api (or application directly)", and it needs no new service credential.
- **Cron expressions through `croniter`** (pure Python, so no ARM64 build problem), as §7.3 shows; one new dependency.
- **Ships with no active schedule**: `deploy/scheduler/schedules.yaml` holds one example with `enabled: false`, so a
  deploy changes nothing until a schedule is enabled on purpose (step 5 enables one for a timed test, then disables
  it).
- **`argus serve` stays** (api + webhook + worker thread in one process) as the rollback; `argus api`, `argus worker`
  and `argus scheduler` are the split.
- **Backup quiet window** (from the PR #25 review): writes by the scheduler and worker change the database while
  `ops/db-backup.sh` takes its before/after fingerprint. Proposed: the backup stops `argus-v18-scheduler` for the
  drill and starts it again (the worker drains nothing new without it). `ops/db-backup.sh` is `conantkd`'s script:
  agree the change with him in the PR.

## Design

- **Claim with a lease (migration `003_worker_lease.sql`):** `incident` gains `claimed_by text` and
  `claimed_until timestamptz`. `claim_next_queued(worker_id, lease_s)` sets both atomically
  (`FOR UPDATE SKIP LOCKED`); the worker renews `claimed_until` while it runs; `requeue_expired()` returns to
  `queued` only runs whose lease has expired (replaces `requeue_running()`, which takes back every run). SQLite keeps
  the same interface for local tests.
- **Resume:** a requeued run is claimed again and `GraphRunner.run` continues after its last checkpoint (T-0013,
  audit `incident.resumed`); no completed read is repeated.
- **Scheduler (`argus/infrastructure/scheduler.py`):** reads and validates `schedules.yaml` (unknown target, bad cron,
  interval below a configured floor ⇒ refuses to start); on each due slot submits a `scheduled` incident with
  idempotency key `sched:<schedule_id>:<scheduled_for>` (§6.6), so a restarted scheduler never submits a slot twice.
  **Skip-if-active:** a target that already has a queued or running incident gets an audit event
  `schedule.coalesced`, no new incident. **Maximum queued age:** the worker closes a scheduled incident not claimed
  within `ARGUS_SCHEDULE_MAX_QUEUED_AGE` as `stale_skipped` without running it. The cadence floor from measured p95
  (§6.5) is a later refinement; for now a fixed minimum interval.
- **Rule 15 guard:** a test proves `argus/infrastructure/scheduler.py` imports no detector, runner, graph or model
  module.
- **Compose (vm-095):** `argus-v18-agent` runs `argus api` (ports unchanged: `127.0.0.1:18000`), new
  `argus-v18-worker` and `argus-v18-scheduler` from the same image, no host ports, on `argus-v18-core`, with memory
  and PID limits. The worker is the only one that reaches executors through the tunnel.
- **Not in scope:** `ReconcileFiringAlerts` (§7.3, behind its feature flag), the concurrency ceiling across several
  workers (one worker for now), daily cost ceilings, OP-004 checkpoint cleanup (after this task).

## Steps

1. **Red: the lease.** Tests (SQLite and Postgres): two workers never claim the same incident; a live lease is not
   taken back; an expired lease is requeued and resumed from its checkpoint without repeating a read. Then migration
   003, store methods, runtime-role grants unchanged (UPDATE on `incident` already exists).
2. **Red: the commands.** `argus api` serves without a worker thread; `argus worker` claims, renews, stops cleanly on
   SIGTERM (finishes or releases the claim); `argus serve` unchanged.
3. **Red: the scheduler.** With a fake clock: due slots submit exactly once (restart included), skip-if-active,
   stale skip, invalid files refused, the import guard.
4. **Compose + ops:** the three containers; `ops/deploy.sh` status lists them; backup quiet window agreed with
   `conantkd`; `docs/` and Brain updated.
5. **VM (vm-095, lease):** state probe → deploy → migrate 003 → rebuild → H-1 through the worker (no model call) →
   kill the worker mid-run, the new worker resumes it → enable one lab schedule for ~30 minutes, see healthy runs and
   one `coalesced`, disable it → NO INTERFERENCE. Rollback: `argus serve` in the agent container, scheduler and
   worker stopped.

## Done when

- The full offline suite and the Postgres tests pass; the red of steps 1-3 is recorded below.
- On vm-095 three Argus containers run from one image; a killed worker's run resumes from its checkpoint; a
  scheduled slot is submitted once and coalesced while the target is busy; NO INTERFERENCE.
- Brain: `CURRENT_STATE.md` (Phase 9), `tdd/CURRENT_TEST_STATE.md`, `IMPLEMENTATION_PLAN.md`, a logbook entry.

## Red seen / evidence

- **Step 1 (2026-10-07): the lease.** `tests/test_worker_lease.py` (8 tests, SQLite) and `test_worker_lease` in
  `tests/test_postgres.py`. Red seen: all 8 failed with `claim_next_queued() got an unexpected keyword argument
  'lease_s'`. Then: migration `003_worker_lease.sql` (`claimed_by`, `claimed_until`, index), `claim_next_queued(worker_id,
  lease_s)`, `renew_claim()`, `requeue_expired()` in both stores and the port; an old SQLite file gets the columns on
  open; `requeue_running()` kept for the single-process `argus serve`. A dead worker's run is requeued only after its
  lease expires and resumes from its checkpoint without repeating the completed read. Suite: 117 passed, 1 skipped
  (Docker-in-Docker backup test), Postgres tests included (throwaway `postgres:16-alpine`).
