# RB-019 — PostgreSQL disk/capacity pressure

## Metadata

```yaml
id: RB-019
title: PostgreSQL disk/capacity pressure
status: draft
owner: Argus Team
version: 1.0.1
created: 2026-09-29
last_reviewed: 2026-10-09
source_review_date: 2026-09-29
last_tested: null
detector: postgresql_storage_pressure
```

## Scope

Declared PostgreSQL 16 data, WAL, tablespace, temporary-file and archive storage, with mapped host filesystems. Verify version, topology/replicas, backup policy and actual mount ownership. Exclude generic Docker cache cleanup of DB volumes and performance-only I/O incidents (RB-010). [Common contracts](../RUNBOOK-CONVENTIONS.md) apply; standalone detection is missing.

## Incident definition

Database-owned storage approaches exhaustion or database writes fail because required storage cannot grow. PostgreSQL disk-full behavior depends on which filesystem fills; loss of WAL space is particularly serious. [PostgreSQL disk-full failure](https://www.postgresql.org/docs/16/disk-full.html)

## User / service impact

Observe failed transactions, unavailable write service, replication/archive lag and threatened recovery objectives. A read-only query or established session succeeding does not prove writes or recoverability are healthy.

## Trigger / detection conditions

Proposed trigger: mapped data/WAL/tablespace available space below a reviewed reserve (lab 10% for 5 minutes), predicted exhaustion within an hour, or corroborated DB disk-full error. Reserve must cover workload, WAL and maintenance peaks; no universal percentage is enough. Required mount/series absent → insufficient_evidence, not zero growth.

## Symptoms

ENOSPC/disk-full messages, growing database/WAL/archive area, write failures, stalled replication/archiving, temporary-file expansion or repeated database startup failure.

## Plausible causes / hypotheses

H1 legitimate relation/index growth; H2 WAL retained by slots/lagging consumers; H3 archive failure/backlog; H4 dead-tuple/bloat/long transaction retention; H5 temporary-query spill; H6 logs or unrelated files on shared mount; H7 inode/quota/storage fault. Total database size does not measure every category.

## Required evidence

DB→data/WAL/tablespace/archive mount mapping and available bytes/inodes; per-category growth; slots/replicas and oldest required WAL; archive health; relation/transaction/maintenance summaries; temporary spill and actual service transaction results. Backup/replication promises are constraints, not expendable disk consumers.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `get_disk_usage(path=None)` | Only supported allowlisted host paths; may not cover database mount | `READ_ONLY_SAFE` |
| `get_disk_history(minutes=60)` | Root space history only; not arbitrary DB tablespaces | `READ_ONLY_SAFE` |
| `inspect_database_health(container)` | DB size, transactions/waits and connection context | `READ_ONLY_SENSITIVE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Bounded redacted database storage errors | `READ_ONLY_SENSITIVE` |
| `get_io_metrics()` | Performance alternative | `READ_ONLY_SAFE` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_db_storage_usage(database_id)` returns approved category sizes and mount IDs; `get_db_wal_retention(database_id)` returns slot/replica retention and restart positions; `get_db_archive_status(database_id)` returns archive backlog/error state; `get_db_maintenance_state(database_id)` returns bounded transaction/vacuum/spill summaries; `get_database_transaction_health(service_id, minutes)` reads existing application-owned transaction-success telemetry. All `READ_ONLY_SENSITIVE`. Shared filesystem history/topology contracts are required. No arbitrary SQL or data-directory walk is a substitute.

## Diagnostic workflow

| Step | Action / reason | Interpretation / next step |
|---|---|---|
| 1 | Bind affected database and failing storage mount | Unknown mount → request mapping; root-space success cannot clear a full tablespace. |
| 2 | Category history and rate/reserve | Relations → H1/H4; WAL → H2/H3; temp → H5; shared logs/other → H6/RB-005. Partial category totals leave alternatives. |
| 3 | For WAL, inspect slots/replicas and archive health | Lagging required consumer/archive failure supports retention mechanism. Do not delete retained segments or drop slots to test it. |
| 4 | For relations/temp, inspect long transactions/maintenance/spills | Supported retention/spill cause → DBA/query owner; size alone is not bloat proof. |
| 5 | Correlate demand/deployment and I/O | Legitimate growth needs capacity; slow storage can amplify backlog. Separate RB-010 from capacity. |
| 6 | Preserve compact evidence; DBA selects capacity/producer/consumer repair | Near-exhaustion with missing detail → urgent escalation, no speculative cleanup. |

## Decision tree

```text
identified DB storage pressure -> which category grows?
relations/indexes -> workload / maintenance / long transactions
WAL -> replication slot/consumer + archive evidence
temporary files -> expensive query/workload evidence
shared logs/other -> owner + RB-005
unknown -> insufficient_evidence; protect all DB files
```

## Evidence interpretation

Replication slots can retain WAL required by consumers; slot metadata and consumer state must inform any intervention. [PostgreSQL replication slots](https://www.postgresql.org/docs/16/view-pg-replication-slots.html), [standby replication](https://www.postgresql.org/docs/16/warm-standby.html) Failed archiving can accumulate retained WAL, so the next check is archive status, not manual segment deletion. [Continuous archiving](https://www.postgresql.org/docs/16/continuous-archiving.html)

## False positives and edge cases

WAL versus relation mount separation, temporary bursts, storage snapshots, sparse files, logical slots, standby lag, existing transactions masking write failures, quota/inodes and missing privilege to inspect stats.

## Diagnosis outcome

All common outcomes permitted. Probable cause names storage category, mount, retaining owner and supporting history; unknown retention/backup implications require escalation even if space is low.

## Mitigation

DBA/platform owner adds reviewed capacity, pauses a proven non-critical producer or repairs an archive/replication consumer. Preserve data and recovery objectives. No default Argus write exists for this class.

## Recovery

Adequate reserve returns on all required mounts, application-owned transactions succeed, and WAL/archive/replication growth is controlled without violating backup objectives.

## Root-cause correction

Fix consumer/archive failures, transaction/query behavior, retention/capacity planning and maintenance. Routine vacuum and `VACUUM FULL` have different space/locking behavior; `VACUUM FULL` can require additional disk and exclusive locking and is not a generic disk-full remedy. [Routine vacuuming](https://www.postgresql.org/docs/16/routine-vacuuming.html)

## Action safety

Storage expansion, query/client stop, slot/retention change, maintenance or DB restart are `MUTATING_HIGH_RISK`. Require exact database/mount/consumer identity, backup/replication owner sign-off, capacity/locking impact and tested recovery plan. Block manual data/WAL deletion, unknown consumer, absent recoverability evidence, missing capability, protected migration/replica or insufficient maintenance headroom. Current Argus escalates, not broadens Docker cleanup scope.

## Human-in-the-Loop

Show reserve/time-to-full, growth category, exact proposed change, affected replicas/backup guarantees and irreversible consequences. Approval to stop a batch client never authorizes dropping a replication slot.

## Forbidden actions

`FORBIDDEN`: delete data/WAL/volume files, unreviewed slot removal, disable fsync/archiving, arbitrary SQL maintenance, VACUUM FULL under unassessed shortage, database restart as cleanup or treat a backup as expendable cache.

## Evidence preservation

Compact redacted category/retention/transaction metadata in a healthy remote sink; no database dumps on the filling disk. Save pre-change replica/archive state and owner constraints.

## Verification

Three distinct fresh post-change storage and transaction-health observations, then 15 minutes of controlled growth plus appropriate archive/replication cycles. Meet configured reserve/time-to-full policy, no new write errors, required consumers progress and backlog declines. Successful DB connect alone is insufficient. Missing transaction/retention telemetry or recurrence prevents closure and escalates.

## Rollback

Capacity expansion may not be reversible; deleted WAL or dropped consumer state may require reinitialization and has no automatic undo. Owner changes retain prior config and tested backup/recovery procedure. Never shrink storage blindly to reverse an expansion.

## Escalation

DBA immediately for WAL/data pressure; storage and backup/replication owners as needed. Attach category/mount growth, consumer identities, recoverability constraints and next missing evidence. Stop any action with unknown data-loss effect.

## Recording / memory

Common record plus data/WAL/tablespace identities, reserve, retaining consumer, backup objectives, transaction recovery and unresolved capacity/maintenance work.

## Prevention / follow-up

Category/mount alerts, slot/archive lag budgets, transaction age control, tested capacity/backup procedures and maintenance sizing.

## Lab validation

Disposable PostgreSQL 16 with a separate capped test data volume: configure a lab-only warning at 80% usage, then generate synthetic data in 8 MiB bounded batches to that threshold; watchdog stops at 85% usage, before uncontrolled database failure. Use a 30-second lab pending duration and retain the bounded data through detection. Separately pause a disposable replication consumer with strict WAL-volume/60-second abort bounds. Expect proposed/unsupported RB-019 selection, H1 versus H2 only with category telemetry, refusal of WAL/volume deletion and no fabricated cleanup. Owner stops fixture/restores consumer or expands only the disposable volume. Verify transaction success/reserve/retention over 15 minutes, record every lifecycle stage and restore snapshot on abort. No database fault was executed.

## References

- [Disk-full failure](https://www.postgresql.org/docs/16/disk-full.html), [replication slots](https://www.postgresql.org/docs/16/view-pg-replication-slots.html), [standbys](https://www.postgresql.org/docs/16/warm-standby.html).
- [Archiving](https://www.postgresql.org/docs/16/continuous-archiving.html), [vacuuming](https://www.postgresql.org/docs/16/routine-vacuuming.html).

## Argus capability gaps

### Missing telemetry

Database mount/category history, retention/consumer health, maintenance/spill and application transaction success.

### Missing tools

`get_db_storage_usage`, `get_db_wal_retention`, `get_db_archive_status`, `get_db_maintenance_state`, `get_database_transaction_health`, shared filesystem tools.

### Tool improvements

Do not equate DB size or root disk history with all database storage; source-aware read-only templates and redacted identities.

### Detector improvements

Category/reserve/time-to-full detector with backup/replication policy and DB-owner permissions.
