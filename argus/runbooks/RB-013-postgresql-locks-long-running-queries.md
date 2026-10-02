# RB-013 — PostgreSQL locks / blocked or long-running queries

## Metadata

```yaml
id: RB-013
title: PostgreSQL locks / blocked or long-running queries
status: draft
owner: Argus Team
version: 1.0.0
created: 2026-09-29
last_reviewed: 2026-09-29
source_review_date: 2026-09-29
last_tested: null
detector: null
```

## Scope

Declared PostgreSQL 16 instance and owned clients; verify major/role permissions before using another version. Include lock waits, long transactions and slow queries; distinguish expected maintenance and approved migrations. [Shared contracts](../RUNBOOK-CONVENTIONS.md) apply. A dedicated detector is missing.

## Incident definition

Queries/transactions exceed their service budget due to blocking or expensive execution. Long duration alone does not establish lock contention; inspect `state`, wait type/event and separate transaction/query/state-change timestamps. [PostgreSQL activity](https://www.postgresql.org/docs/16/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW)

## User / service impact

Observe latency, blocked requests and connection retention. A long-running report may be expected; one idle transaction can harm unrelated writers. Identify blocked victims and actual blocking owner separately.

## Trigger / detection conditions

Proposed candidate: lock wait above a route-specific budget (lab starting point 30 seconds) or transaction/query duration above its owned workload budget, sustained over two fresh observations with impact. A generic global “long query” threshold is insufficient. Missing activity privilege or stale cache is unknown, not no blockers.

## Symptoms

Growing lock waits, blocked transactions, slow completion, timeout/deadlock errors, retained slots and idle transactions.

## Plausible causes / hypotheses

H1 abandoned idle transaction holds locks; H2 long active transaction; H3 migration/DDL locks; H4 incompatible access order/deadlock; H5 expensive unblocked query; H6 I/O/CPU bottleneck; H7 normal long job or misleading telemetry.

## Required evidence

DB identity, session PID/backend start, role/application/address, transaction/query/state ages, sanitized query fingerprint, wait type/event, blocker graph with protected owners, relation category, workload budget and CPU/I/O timeline. Do not infer blocker identity from a total wait count.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `inspect_database_health(container)` | Summary wait count and long transactions; incomplete graph | `READ_ONLY_SENSITIVE` |
| `get_db_connection_history(database, minutes=30)` | Slots retained during blocking | `READ_ONLY_SENSITIVE` |
| `get_cpu_history(container, minutes=30)` / `get_io_metrics()` | CPU/I/O alternative | `READ_ONLY_SAFE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Redacted timeout/deadlock context | `READ_ONLY_SENSITIVE` |
| `correlate_incident_timeline(container, minutes=30)` | Timing relative to other failures | `READ_ONLY_SENSITIVE` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_db_activity(database_id, limit)` with session/start identity and redacted fingerprint; `get_db_lock_graph(database_id, limit)` using bounded `pg_blocking_pids`/lock metadata and explicit truncation; `get_db_long_transactions(database_id, min_age, limit)` with state/transaction ages. All `READ_ONLY_SENSITIVE`, fixed SQL templates through a monitor role, no arbitrary SQL. PostgreSQL's blocking function is preferable to guessed self-joins over lock modes. [System information functions](https://www.postgresql.org/docs/16/functions-info.html), [pg_locks](https://www.postgresql.org/docs/16/view-pg-locks.html)

## Diagnostic workflow

| Step | Action / why | Interpretation / next step |
|---|---|---|
| 1 | Activity and workload budget | Expected authorized long job without impact → observe. Real breach → 2; missing detailed view → record gap. |
| 2 | Wait type/event and CPU/I/O evidence | Lock wait → 3. Running computation/storage wait → H5/H6, RB-006/010. No wait data → multiple hypotheses. |
| 3 | Bounded blocker graph and session identity | Follow blocked→blocking edges to an attributable owner; protect migrations/critical/system work. Truncated graph cannot establish root blocker. |
| 4 | Compare transaction state and owner intent | Old idle transaction supports H1, active long work H2, declared migration H3. Deadlock requires matching DB evidence, not a guessed cycle from stale snapshots. |
| 5 | Correlate victim/slot pressure and preserve graph | Exhaustion secondary to blocking → RB-004 linked incident; do not stop arbitrary victims. |
| 6 | DBA reviews exact corrective action, then fresh graph/request checks | No bounded cancellation/termination authority → escalate; no generic SQL fallback. |

## Decision tree

```text
budget exceeded with impact?
  no -> expected workload / wrong runbook
  yes -> lock wait? no -> compute/I/O/query diagnosis
           yes -> blocker identified and owned?
                    no -> insufficient_evidence; obtain graph
                    yes -> idle / active / migration / protected transaction
                           -> owner completion/cancel plan; verify victims
```

## Evidence interpretation

Locks normally persist until transaction end; canceling one statement is not equivalent to ending the session/transaction or necessarily releasing all locks. Cancellation and termination have different effects and privileges. [PostgreSQL locking](https://www.postgresql.org/docs/16/explicit-locking.html), [server signaling](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-ADMIN-SIGNAL)

## False positives and edge cases

Prepared transactions, parallel workers, PID reuse, stale graph, query already completed, canceled statement with transaction still open, low monitor visibility, maintenance/replication roles and query text containing customer data.

## Diagnosis outcome

All common outcomes allowed. Probable blocking cause needs graph identity, ownership/state and victim linkage; long duration alone is insufficient. Record unresolved expensive-query versus storage hypotheses separately.

## Mitigation

DBA/application owner may complete/rollback an owned transaction or cancel a reviewed query. Generic session termination is not available. Existing `db.terminate_idle_in_transaction` is restricted to its RB-004 client case and is not an arbitrary blocker-removal API.

## Recovery

Intended blocked work resumes, queue/lock waits subside, ordinary clients succeed and retry traffic stays bounded. Killing a victim without removing the blocker is not recovery.

## Root-cause correction

Fix transaction lifecycle/order, reduce transaction scope, schedule safe migrations, tune proven expensive queries/indexes and apply role-specific timeouts with workload testing.

## Action safety

Cancel/terminate/transaction rollback/config changes are `MUTATING_HIGH_RISK`. Require exact DB, PID/backend start, role/address, query/transaction identity, lock graph, business-owner approval, protected migration/system/critical roles and immediate state recheck. Cap candidates and one action. Block reused/disappeared identity, unknown side effects, incomplete graph, protected owner or missing deterministic guards. Query cancellation/termination contracts are missing; current default is owner escalation.

## Human-in-the-Loop

Show the exact blocker and affected victims, rollback/data-loss/retry implications, why waiting is unacceptable and how lock release will be verified. No approval for “kill long queries” or a reusable PID-only action.

## Forbidden actions

`FORBIDDEN`: arbitrary SQL/session kills, database restart to clear locks, blanket timeout changes, kill all old sessions, terminate migrations/replication or expose raw query literals.

## Evidence preservation

Save bounded graph/activity fingerprints, timestamps and owner classification before intervention. Redact query text before model/storage; retain privilege/truncation gaps.

## Verification

Three source-fresh graph/activity and service observations after action, then 5 minutes: targeted blocking edge gone, intended workload completes, no equivalent replacement blocker, ordinary admission healthy and retries/errors near baseline. Successful signal delivery alone fails recovery criteria. Changed blocker identity, stale graph or recurrence escalates.

## Rollback

Canceled/terminated work cannot be reconstructed automatically. Application owner retries only idempotent/compensated work; no blind transaction replay. Restore timeout/config only through a reviewed change that does not reintroduce contention.

## Escalation

DBA plus transaction/migration owner. Stop when blocker ownership is unknown, graph truncated, action result ambiguous or wait returns. Attach redacted graph, identities/ages, victim impact and requested owner decision.

## Recording / memory

Common record plus blocked/blocker identities, wait semantics, protected candidates, intervention effects and unresolved transaction/query defect.

## Prevention / follow-up

Short bounded transactions, consistent lock order, migration budgets, application timeout discipline and monitor-role graph visibility.

## Lab validation

Disposable database/table: session A begins a transaction and updates one synthetic row without ending it; session B updates the same row with a fixed 60-second statement timeout. Record timestamps and ground truth; watchdog rolls back A after 90 seconds. Expect lock-wait candidate, RB-013 and A as blocker only if graph tool exists; summary-only evidence must not invent A. Mark A protected in a second case to require refusal. DBA-approved fixture rollback releases B or allows a safe test retry; denied approval causes no Argus write. Verify fresh graph and service success for 5 minutes and record all stages. Repeat an unblocked slow query to avoid automatic lock diagnosis. Not executed.

## References

- [PostgreSQL explicit locking](https://www.postgresql.org/docs/16/explicit-locking.html), [pg_locks](https://www.postgresql.org/docs/16/view-pg-locks.html), [blocking functions](https://www.postgresql.org/docs/16/functions-info.html).
- [Activity](https://www.postgresql.org/docs/16/monitoring-stats.html), [server signaling](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-ADMIN-SIGNAL).

## Argus capability gaps

### Missing telemetry

Bounded blocker graph, immutable session identity, precise wait/age semantics and protected owners.

### Missing tools

`get_db_activity`, `get_db_lock_graph`, `get_db_long_transactions`; separately designed cancellation capability if approved later.

### Tool improvements

Sanitized query fingerprints, source freshness/privilege coverage and deterministic candidate revalidation.

### Detector improvements

Impact/budget-aware wait detector; distinguish lock, computation, I/O and legitimate maintenance.
