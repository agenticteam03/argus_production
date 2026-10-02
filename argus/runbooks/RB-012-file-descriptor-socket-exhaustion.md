# RB-012 — File descriptor / socket exhaustion

## Metadata

```yaml
id: RB-012
title: File descriptor / socket exhaustion
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

Linux processes in declared Docker workloads. Record host/container identity, host PID plus process start time, network namespace, kernel and effective limits. Separate per-process descriptors, host file handles, socket state, listen backlog and ephemeral ports. [Common contracts](../RUNBOOK-CONVENTIONS.md) apply; this detector is missing.

## Incident definition

New files or connections cannot be acquired because the applicable resource boundary is exhausted. `RLIMIT_NOFILE` constrains descriptors; exceeding it can produce `EMFILE`. A process descriptor limit is not a general socket-capacity measurement. [Linux resource limits](https://man7.org/linux/man-pages/man2/getrlimit.2.html)

## User / service impact

Failed accepts/connects/file opens, unavailable requests and degraded logging. Establish which process and request path is affected; many open connections can be normal.

## Trigger / detection conditions

Proposed warning: descriptor usage above 80% of effective soft limit for 5 minutes with rising trend; critical on corroborated acquisition failure. Socket/port backlog errors need their own measured boundary. Unknown limit, missing FD observation or replaced PID must not yield a ratio. No dedicated current detector exists.

## Symptoms

Too-many-open-files errors, stalled accepts, connection acquisition failures, growing file/socket counts and loss of useful throughput.

## Plausible causes / hypotheses

H1 descriptor leak; H2 legitimate concurrency exceeds limit; H3 oversized/unbounded pools; H4 slow peer keeps connections occupied; H5 host-wide handle pressure; H6 ephemeral-port/listen-backlog issue; H7 low configured process limit. Namespace socket counts alone cannot distinguish these.

## Required evidence

Exact sanitized error, per-process open count and soft/hard limit, process start identity, trend at comparable demand, descriptor categories, socket states/destinations, host handles, port/backlog pressure and pool/peer health. Do not retrieve file contents through descriptor links.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `get_container_processes(container)` | Obtain current host PID and process ownership | `READ_ONLY_SENSITIVE` |
| `inspect_process_details(container, pid)` | Ownership-checked current FD/socket counts, age/status | `READ_ONLY_SENSITIVE` |
| `get_socket_summary(container)` | Namespace-level TCP states and destinations, not per-PID attribution | `READ_ONLY_SENSITIVE` |
| `get_network_history(container, minutes=30)` | Traffic context; missing-error fields are unreliable | `READ_ONLY_SAFE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Exact resource-acquisition error | `READ_ONLY_SENSITIVE` |
| `capture_diagnostic_snapshot(container)` | Preserve current process state | `READ_ONLY_SENSITIVE` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_fd_limits(container, pid, process_start_id)` returns effective process limits and host handle capacity; `get_process_fd_usage(container, pid, process_start_id, minutes)` adds bounded count/category history; `get_socket_capacity(container)` exposes configured port/backlog bounds and errors. All `READ_ONLY_SENSITIVE`, identity-checked, without descriptor targets containing secrets or file contents. Current `inspect_process_details` lacks limits/history and robust explicit start-identity binding.

## Diagnostic workflow

| Step | Action / reason | Interpretation / next step |
|---|---|---|
| 1 | Error plus process identity | File-acquisition error and correct live process → 2. Process replaced → rebind and preserve old evidence. |
| 2 | Current FD count versus effective limit/history | Near process limit supports H1/H2/H7. Missing limit → insufficient attribution, not assumed default. |
| 3 | Categorize descriptors and correlate demand | Persistent growth at stable traffic supports leak; bounded peak tracks useful work → capacity/pool sizing. |
| 4 | Namespace socket states, pool/peer health | Slow peer or pool accumulation supports H3/H4; numerous socket states alone do not prove open-FD leak. |
| 5 | Host/port/backlog constraints if process has headroom | H5/H6 requires its own measured limit/error; request missing capability rather than tuning kernel blindly. |
| 6 | Preserve evidence; choose owner mitigation | Unknown boundary/owner → no restart/limit increase. Proven process leak may justify one separately permitted restart. |

## Decision tree

```text
process count near known FD limit + matching error? -> leak / demand / low limit
  no -> host handle or socket/port/backlog boundary measured?
          yes -> boundary-specific investigation
          no -> insufficient_evidence
count grows with stable demand? -> retention hypothesis
slow dependency/pool backlog? -> fix owner/peer, protect victim
```

## Evidence interpretation

`/proc/<pid>/fd` describes descriptors held by that process; network-namespace tables are a different scope. Do not equate all namespace sockets with one application's open descriptors. [Linux process descriptors](https://man7.org/linux/man-pages/man5/proc_pid_fd.5.html) TCP state/queue behavior and kernel tuning are version-dependent; do not derive a safe tuning change from a count alone. [Linux TCP](https://man7.org/linux/man-pages/man7/tcp.7.html)

## False positives and edge cases

Shared namespaces, short-lived PID reuse, expected large pool, brief load burst, inaccessible `/proc`, FD count changing during collection, many TIME_WAIT entries without corresponding process-held descriptors and unknown IPv6 addresses in current summary.

## Diagnosis outcome

All common outcomes allowed. A probable leak requires persistent attributed growth and lifecycle evidence; one near-limit count supports exhaustion only. Keep host/process/port boundaries explicitly separate.

## Mitigation

Owner can reduce non-critical concurrency or refresh an evidenced leaking process through a permitted restart. Raising a limit without demand/host assessment may merely defer failure. No generic kernel tuning is available.

## Recovery

New connections/files and representative requests succeed, descriptor/socket demand stabilizes with adequate headroom, and dependencies remain healthy.

## Root-cause correction

Close resources reliably, bound pools/timeouts, repair peer stalls or set a reviewed process capacity limit matching tested demand and host resources.

## Action safety

Restart, concurrency/limit/pool change are `MUTATING_HIGH_RISK`. Bind exact container/process identity, preserve counts/categories, assess in-flight loss and peer reconnect load, protect critical services and require a supported capability/gate. Block guessed limit values, absent ownership, unresolved dependency, missing predicate enforcement or unsupported class. Limit changes remain operator procedures.

## Human-in-the-Loop

Show measured boundary, count/limit/trend, exact operation and expected reconnect/work-loss risk. Approval of restart does not approve raising system limits. Expiry/identity change cancels the write.

## Forbidden actions

`FORBIDDEN`: arbitrary kill, global file/socket sysctl changes, unlimited ulimit, forcibly close unknown descriptors, expose descriptor file contents, or blindly reset connections.

## Evidence preservation

Save bounded descriptor categories/counts, process start identity, errors and peer/traffic windows before restart. Snapshot alone lacks the missing limits/history, which must be separately attached or marked absent.

## Verification

Three fresh post-action observations, then at least 5 minutes and one pool reuse/timeout cycle under representative demand. Acquisition errors disappear, FD use stays below the calibrated budget (lab recovery starting point 70%), good throughput returns and no rapid regrowth occurs. Missing limits/history prevents a durable-resolution claim. Recurrence/timeout escalates.

## Rollback

Restart cannot restore lost sessions. Owner retains previous limit/pool configuration; lowering limits requires confirming live demand is safe. Each resume/config reversal is separately approved.

## Escalation

Application owner for leaks/pools, platform/network owner for host handles/ports/backlogs. Attach identity, exact error, scope/limit uncertainty, workload trend and next missing capacity measurement. Stop speculative changes.

## Recording / memory

Common record plus affected resource boundary, count/limit, process start identity, socket scope and whether leak correction remains outstanding.

## Prevention / follow-up

Resource-lifecycle tests, FD/connection budgets, peer timeouts, descriptor/limit telemetry and safe process identity checks.

## Lab validation

Disposable process soft limit 128; fixture opens one harmless descriptor every 100 ms, capped at 140 attempts and 60 seconds. Expect EMFILE/count approach if evidence tools exist; no fabricated FD limit if they do not. Compare a fixture with a stable bounded pool. Require proposed/unsupported RB-012 selection, no global limit change, denied restart → zero write. Operator closes fixture handles/fixes lifecycle; an independently permitted restart may be tested with new approval. Verify fresh acquisition and stable demand for 5 minutes; replay PID reuse to require refusal. Record every lifecycle stage; not executed.

## References

- [Linux resource limits](https://man7.org/linux/man-pages/man2/getrlimit.2.html), [process descriptors](https://man7.org/linux/man-pages/man5/proc_pid_fd.5.html), [TCP](https://man7.org/linux/man-pages/man7/tcp.7.html).
- [Argus assessment](../RUNBOOK-ASSESSMENT.md) — current process/socket tool scope.

## Argus capability gaps

### Missing telemetry

Effective limits, historical/categories of FDs, host handle/port/backlog capacity and process start identity.

### Missing tools

`get_fd_limits`, `get_process_fd_usage`, `get_socket_capacity`.

### Tool improvements

Bind PID plus start identity; distinguish process and namespace scope; preserve IPv6/permission failures as unknown.

### Detector improvements

Resource-boundary-specific detector with known denominator, duration, identity and fresh error evidence.
