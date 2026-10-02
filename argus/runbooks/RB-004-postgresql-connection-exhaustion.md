# RB-004 — PostgreSQL connection exhaustion

## Metadata

```yaml
id: RB-004
title: PostgreSQL connection exhaustion
status: draft
owner: Argus Team
version: 1.0.0
created: 2026-09-29
last_reviewed: 2026-09-29
source_review_date: 2026-09-29
last_tested: null
detector: null
parent_detector: dependency_unavailable
```

## Scope

PostgreSQL 16 and declared application clients on Host T. For other majors review matching admission/role settings. Distinguish pooler capacity from server capacity; this procedure assumes direct PostgreSQL observations and needs pooler telemetry when one intervenes. Apply [common contracts](../RUNBOOK-CONVENTIONS.md). No standalone RB-004 detector exists in inspected code.

## Incident definition

Ordinary application sessions are rejected because usable connection capacity is exhausted. SQLSTATE `53300` is `too_many_connections`; connection refusal, authentication error or timeout alone does not prove this condition. [PostgreSQL error codes](https://www.postgresql.org/docs/16/errcodes-appendix.html)

## User / service impact

New requests/jobs cannot acquire sessions; existing pooled work may continue. Establish affected roles/routes and pool wait time; a live database and successful privileged monitor can coexist with user failure.

## Trigger / detection conditions

Branch from RB-003 when fresh victim errors report admission failure and database capacity corroborates it. Proposed standalone warning: ordinary-slot utilization above 90% for 5 minutes, with critical selection on actual admission failure. These values are calibration defaults, not deployed rules. Role/database/pool limits can cause earlier rejection; unknown capacity must not be divided into a misleading ratio.

## Symptoms

`53300`, reserved-slot messages, rising session count, pool acquisition timeouts, many sessions attributed to one client, old transactions or reconnect bursts.

## Plausible causes / hypotheses

H1 legitimate concurrent demand; H2 retained/leaked sessions; H3 idle transactions; H4 aggregate pool maxima oversized after scale-out; H5 retry/reconnect storm; H6 client defect; H7 role/database/pooler-specific limit rather than global exhaustion. H3 is an observed state, not automatic evidence of H2/H6. Session state, wait event and transaction age are separate dimensions. [PostgreSQL activity statistics](https://www.postgresql.org/docs/16/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW)

## Required evidence

Exact SQLSTATE and role context; version, configured/reserved capacity, counts by backend type/application/role/address/state; `state_change`, transaction age and wait events; historical growth, pool settings/replicas and workload/retry history; fresh ordinary-role admission. Corroborate `application_name` with role/address and owned workload: the name alone is not a secure identity.

## Required Argus tools

| Existing tool / input | Purpose / relevant output | Safety class |
|---|---|---|
| `inspect_database_health(container)` | Capacity, states, application groups, long transactions and wait counts | `READ_ONLY_SENSITIVE` |
| `get_db_connection_history(database, minutes=30)` | Per-application growth and coverage | `READ_ONLY_SENSITIVE` |
| `get_socket_summary(container)` | Client-namespace socket groups; not proof of one process's ownership | `READ_ONLY_SENSITIVE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | SQLSTATE, pool/retry errors after redaction | `READ_ONLY_SENSITIVE` |
| `inspect_service_config(container, config='main')` | Declared allowlisted pool configuration; no env dump | `READ_ONLY_SENSITIVE` |
| `correlate_incident_timeline(container, minutes=30)` | Growth versus victim error timing | `READ_ONLY_SENSITIVE` |
| `capture_diagnostic_snapshot(container)` | Client state before containment | `READ_ONLY_SENSITIVE` |
| `scale_service(container, replicas=0)` | Registered single-container stop; lab gate only for named worker | `MUTATING_HIGH_RISK` |
| `execute_runbook_action(action, database, application_name, min_idle_seconds)` | Registered `db.terminate_idle_in_transaction`; requires additional predicates below | `MUTATING_HIGH_RISK` |

The two writes exceed the restart-only production architecture. Their presence in the lab registry is not production authorization. The inspected lab gate allows only specific targets and incident classes, not a new invented RB-004 class.

## Missing tools

**MISSING TOOL REQUIREMENT:** `check_database_admission(database_id, role_profile)` performs one bounded ordinary-role connect and harmless read, returning SQLSTATE/source time with no credentials. **MISSING TOOL REQUIREMENT:** `get_db_activity(database_id, limit)` returns redacted session identity (`pid`, `backend_start`), role/address/state and age, and `get_pool_history(service_id, minutes)` exposes active/idle/waiting/pool limits. All are `READ_ONLY_SENSITIVE`. Existing health summaries are useful but do not provide an approval-bound exact session set or pooler diagnosis.

## Diagnostic workflow

| Step | Action / purpose | Interpretation and next step |
|---|---|---|
| 1 | Obtain victim SQLSTATE plus dependency TCP/protocol state | Not admission exhaustion → RB-003. Confirmed/possible slot issue → 2. |
| 2 | Read health and role/version settings; request ordinary admission | Compute capacity relevant to the client, not privileged monitor. Missing privilege/role semantics → insufficient capacity evidence; continue bounded reads. |
| 3 | Read connection history and activity groups | Uniform active growth follows demand → H1. One group accumulating retained sessions → H2/H3; many clients reconnecting → H5. |
| 4 | Compare pools × replicas, client sockets and transaction state | Pool envelope exceeds budget → H4. Persistent old idle transactions plus repeated client growth support defective lifecycle; ordinary idle pooled sessions alone do not. |
| 5 | Correlate changes/load and waits | Slow/blocked transactions may retain capacity secondarily → RB-013. Preserve alternatives if growth predates available history. |
| 6 | Snapshot client and DB evidence; choose bounded containment | Stop only a proven, explicitly non-critical producer under an accepted profile; otherwise DBA escalation. Session termination is a separate guarded proposal. |
| 7 | Verify new admission and victims, then watch recurrence | Freed slots without fixed client behavior are temporary containment. |

## Decision tree

```text
ordinary admission rejected?
  no -> pool/application/network branch or stale event
  yes -> global ordinary capacity full?
           no -> role/database/pooler limit or authentication; investigate
           yes -> one client growing? -> ownership + session-state investigation
                  all active with load? -> capacity/concurrency
                  pools oversized? -> pool budget
                  rapid reconnects? -> retry storm
         safe owned non-critical source + enforced policy? -> HITL containment
         otherwise -> DBA / insufficient_evidence
```

## Evidence interpretation

For PostgreSQL 16, ordinary capacity must account for both `reserved_connections` and `superuser_reserved_connections`, with the caller's role privileges considered. Do not assume a fixed subtraction of three. [PostgreSQL connection settings](https://www.postgresql.org/docs/16/runtime-config-connection.html)

Monotonic session growth at steady workload supports a leak hypothesis; long transactions can instead reflect locks or legitimate work. Monitor-view “accepting” in current code is a count calculation, not a connection test.

## False positives and edge cases

Connection pool startup, failover storm, spoofed/shared application names, NAT/shared client address, monitor reserve, low role limit, dropped sampling, stale cached DB response, pooler multiplexing, prepared transactions and insufficient monitor privileges. Query text can contain secrets/business data; do not send raw query literals to the model.

## Diagnosis outcome

Allow all five common outcomes. A probable client defect needs ownership, growth and lifecycle evidence, plus counterevidence against demand/locks. Otherwise record the observable exhaustion and unresolved mechanism explicitly.

## Mitigation

Contain an approved non-critical leaking client; this is **containment/recovery**, not a durable fix. Operator-controlled backoff/load reduction can reduce admission pressure. Terminating eligible idle sessions may briefly free slots but the client can recreate them.

## Recovery

Ordinary clients can establish fresh sessions and complete requests; capacity has sustained headroom and pool wait time returns toward baseline. A stopped batch workload represents reduced functionality and must be recorded.

## Root-cause correction

Repair transaction commit/rollback/close discipline, bounded pool sizing across replicas, retry budgets and timeouts appropriate to the application. PostgreSQL idle-session/transaction settings have different effects; validate with pool behavior and deployed version rather than setting a universal timeout. [Client connection defaults](https://www.postgresql.org/docs/16/runtime-config-client.html)

## Action safety

| Write | Exact bounds / prerequisites | Risk and execution blocks |
|---|---|---|
| `scale_service(container, replicas=0)` | Accepted broader profile; named non-critical owner, snapshot, proven harmful contribution; one stop | Lost batch work/backlog; protect API, DB, migration, monitor/control plane. Block unknown ownership, client still needed for recovery or production restart-only profile. |
| `execute_runbook_action(action='db.terminate_idle_in_transaction', database, application_name, min_idle_seconds)` | Exact DB identity; allowlisted client **and** role/address; approved session identities and backend start times; still idle-in-transaction; age threshold rechecked; candidate-count cap | Rolls back work and may cause reconnects. Block protected roles/apps, changed/reused PID, active transactions, ambiguous DB binding or missing server-side candidate revalidation. |

Both are `MUTATING_HIGH_RISK`. Proposed minimum idle age is 60 seconds for lab calibration (existing schema allows 30–86400); it is not proof a session is disposable. Protected names include `postgres`, `migration-runner`, `critical-api`, plus actual topology owners. Application name alone cannot authorize termination. The present signature does not bind a session set, so this release requirement is missing and production execution stays blocked.

## Human-in-the-Loop

Approval identifies source client/DB, exact stop or candidate session set, rolled-back-work risk, denied/protected candidates, expected freed capacity and recurrence plan. Stopping a worker does not approve terminating sessions or restarting it later. The approver must own the affected scope.

## Forbidden actions

`FORBIDDEN`: restart database/victims to clear slots; terminate arbitrary sessions; unrestricted SQL; trust application name as authenticated identity; increase `max_connections` without memory/capacity review; expose connection strings; label a stopped defective client permanently fixed.

## Evidence preservation

Save redacted session grouping/identities, pool config fingerprint, 30-minute history and client snapshot before stop/termination. Preserve no business rows or credentials. Record missing session details as an action blocker.

## Verification

After the completed action, three distinct fresh admission/capacity samples and victim requests; then at least 5 minutes and one normal pool-recycle interval. Proposed headroom target: utilization below 80%, calibrated to required burst capacity. No renewed connection growth/admission error; intended client stop confirmed if used. A privileged monitor alone cannot pass. Recurrence, stale cache or missing admission tool prevents closure and triggers DBA escalation.

## Rollback

Terminated sessions/rolled-back transactions cannot be restored automatically. Starting a stopped client is a new approved action after correction or with a reviewed bounded pool; otherwise it recreates the incident. Preserve previous pool/timeout configuration for owner-managed rollback.

## Escalation

DBA and client owner for ambiguous ownership, protected sessions, missing predicates, failed containment or recurrence. Attach role-specific capacity, client/session evidence, failed admission, lock alternatives and approval/action state; request a reviewed exact session set or pool diagnosis next.

## Recording / memory

Common record plus ordinary versus reserved capacity, client attribution confidence, transaction state/age, stopped functionality, freed slots, admission proof and unresolved lifecycle defect.

## Prevention / follow-up

Budget aggregate pools, bound retry storms, alert on per-client growth, test transaction cleanup and protect monitor capacity with least-privilege roles. Session cancellation/termination behavior must be assessed by the DBA. [PostgreSQL server signaling](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-ADMIN-SIGNAL)

## Lab validation

Disposable PostgreSQL 16 with `max_connections=20`, 3 superuser-reserved slots, 0 extra reserved slots; a dedicated ordinary test role opens and retains one transaction per second, capped at 20 attempts. Use a separate monitor and synthetic API. Expect fresh `53300`, growing client/idle-transaction counts and RB-004→RB-005 selection. Record whether code labels are only calculated. Deny a stop proposal: zero writes; then separately approve one exact non-critical fixture stop under the lab profile. Termination lacking bound candidates must be refused, including a forged application name and PID reuse fixture. Verify ordinary connection/request recovery for 5 minutes, record containment not cure, and restore only disposable lab data. Repeat with legitimate active sessions and oversized idle pools: do not call either a proven leak. Tests are specified, not run.

## References

- [PostgreSQL 16 errors](https://www.postgresql.org/docs/16/errcodes-appendix.html), [activity statistics](https://www.postgresql.org/docs/16/monitoring-stats.html), [connection settings](https://www.postgresql.org/docs/16/runtime-config-connection.html).
- [Client timeouts](https://www.postgresql.org/docs/16/runtime-config-client.html) and [server signaling](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-ADMIN-SIGNAL).
- [Argus assessment](../RUNBOOK-ASSESSMENT.md) — lab profile, policy and monitor limitations.

## Argus capability gaps

### Missing telemetry

Ordinary-role admission, pool demand/waiters, source timestamps, exact candidate identity and role-aware capacity.

### Missing tools

`check_database_admission`, `get_db_activity`, `get_pool_history`.

### Tool improvements

Redact query literals; distinguish calculated/observed acceptance; bind DB and candidate sessions, protected roles, count cap, state/age recheck and immutable backend identity in the termination gateway.

### Detector improvements

Standalone capacity/admission detector and alert are missing; preserve RB-003 branching. Evaluate stop/termination prerequisites in deterministic code; prose preconditions are insufficient.
