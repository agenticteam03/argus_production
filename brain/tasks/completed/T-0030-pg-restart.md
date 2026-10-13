# T-0030 — Phase 13: a Postgres restart is a pause, never a crash

| Field | Value |
|---|---|
| Status | `done` 2026-10-10 (a restart mid-run and a 30 s outage on vm-095: no Argus container restarted); PR #62 merged |
| Phase | 13 — failure and recovery ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md): "Postgres restart"; failures are escalations, never crashes) |
| Architecture | no change (§6.2: the worker's lease, resume from the checkpoint) |
| Branch | `task/T-0030-pg-restart`, from `main`; the VM proof ran on `task/T-0030-vm-proof` |
| Owner | `conantkd` (+ agent) |

## Goal (plain language)

While Postgres restarts, every database call fails. Argus must pause and go on, not crash: no lost run, no
container restart, no wrong outcome.

## Found and fixed

The scheduler already guarded its tick and its alert pass; the worker's loop did not. An error from `recover()` or
from claiming the next incident ended `run_forever`, so Docker had to restart the worker. Now it logs
`database call failed; retry in N s`, waits `db_retry_s` (5 s, interruptible by stop) and retries.

## Steps

1. **Code and tests** (done): `tests/test_t0030_pg_restart.py` (3; red seen: the loop died on a database error).
2. **vm-095** (done, [evidence](../../execution/history/T-0030/step-02/evidence.md)): a restart during an SC-03 run
   (the run DIAGNOSED) and a 30 s outage (the worker logged one retry and went on; the scheduler resumed; the api
   answered); restarts 0; NO INTERFERENCE.

## Not covered (next in phase 13)

Prometheus down on one host (the other host must go on); executor token rotation. The single-process `argus serve`
(the rollback mode) has its own loop without this guard.
