# OP-004 — Checkpoint retention

**Owner:** `conantkd` · **Branch:** `task/OP-004-checkpoint-cleanup` · **Status:** offline implementation verified; VM dry run pending.

## Goal

Keep the LangGraph checkpoints of active or recently closed investigations, and remove all three checkpoint tables'
rows for incidents that became final more than 30 days ago. Keep incidents, evidence, audit, and run events.

## Accepted design and limits

- `argus db prune-checkpoints` runs as `argus_owner`; the runtime role still has no DELETE grant.
- The command is read-only by default. `--apply` is required to remove rows. The cutoff is based on
  `body->>'closed_at'`; a final incident without this value is kept.
- One transaction removes checkpoints, blobs, and writes and appends `maintenance.checkpoints_pruned` as a standard
  audit record (`category=decision`, `actor=system`). Failure rolls the transaction back.
- `ops/checkpoint-retention.sh` mounts only the owner's database credential into a one-off Argus image. Manual runs
  require the VM session marker; the daily `argus-v18-*` systemd timer is shipped but not installed yet.
- **`--scheduled` skips the lease check** (a timer holds no lease), so once enabled it may delete rows while someone
  else holds vm-095. Enabling the timer is therefore an explicit team decision: either make the scheduled run skip
  with a log line when `/opt/argus-v18/SESSION` names a holder, or record in PARALLEL_LANES that this one maintenance
  job runs without a lease (review of PR #42).
- The apply lock is `pg_advisory_xact_lock(404, 1)`: the two-key form (OP-004, job 1), a separate lock space from the
  one-key `hashtext(incident_id)` locks in `postgres_store.py`.

## Steps

1. **Offline, done:** tests red before the command existed, then green against a throwaway PostgreSQL 16. They cover
   dry run, old final incidents, recent and active incidents, missing `closed_at`, all three checkpoint tables,
   preserved incident/run-event/audit rows, a second run, rollback on audit failure, runtime-role refusal, and the
   wrapper's lease check.
2. **VM dry run, pending:** take the VM lease; run the state probe and `nonint-check.sh before` on vm-095; confirm a
   restorable backup; deploy or build the maintenance image from this branch; run the default dry run; record row counts
   and `NO INTERFERENCE`. Do not delete live database rows in this step.
3. **Apply and timer, pending teammate decision:** review the dry-run counts and backup evidence with a teammate before
   any deletion. Then run one bounded `--apply`, verify rows and audit, and install/enable the daily timer if accepted.

## Acceptance

- Old final threads are removed from all three checkpoint tables; active, recent, and undated threads remain.
- The runtime role cannot run the command or DELETE checkpoints.
- A dry run makes no database change; an apply is atomic and leaves evidence and audit intact.
- The VM dry run, approved apply, timer enablement, and `NO INTERFERENCE` are recorded before OP-004 is marked fixed.
