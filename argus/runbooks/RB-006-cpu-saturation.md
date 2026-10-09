# RB-006 — CPU saturation

## Metadata

```yaml
id: RB-006
title: CPU saturation
status: draft
owner: Argus Team
version: 1.0.1
created: 2026-09-29
last_reviewed: 2026-10-09
source_review_date: 2026-09-29
last_tested: null
detector: cpu_saturation
```

## Scope

Host T Linux CPUs and Docker workload CPU budgets. Record logical CPU count, affinity/quota, kernel/cgroup and metric versions. Distinguish host contention from a throttled workload with idle host capacity. [Common contracts](../RUNBOOK-CONVENTIONS.md) apply; this incident class is not implemented.

## Incident definition

Runnable work cannot receive sufficient CPU within the service's required latency/throughput budget. High utilization alone can be legitimate useful work. Load average includes runnable tasks and tasks waiting for disk I/O, so load alone is not CPU saturation. [Linux load average](https://man7.org/linux/man-pages/man5/proc_loadavg.5.html)

## User / service impact

Measure latency, completed work, errors and queue growth. A busy batch CPU with normal deadlines is not necessarily a service incident. Record unknown impact when request/job telemetry is absent.

## Trigger / detection conditions

Proposed candidate: host busy above 90% for 5 minutes with CPU pressure or worsening service performance; separately detect sustained container throttling with impact even when host utilization is low. Normalize to available capacity and keep these two triggers separate. Three distinct samples and valid coverage are minimum evidence; missing CPU or quota data is unknown. Thresholds require calibration and a new detector/alert.

## Symptoms

High busy time, runnable backlog, CPU pressure, throttling, slow requests and delayed jobs; high I/O wait may instead indicate RB-010.

## Plausible causes / hypotheses

H1 legitimate traffic/work increase; H2 runaway/busy loop; H3 excessive concurrency/retries; H4 expensive request/query; H5 restrictive CPU quota/affinity; H6 noisy neighbor/host contention; H7 I/O-related load mistaken for CPU demand.

## Required evidence

Host and container CPU histories with units, CPU/affinity/quota definitions, pressure and throttling deltas, process attribution, load/I/O context, traffic/completions/latency and deployment history. A process ranking alone cannot distinguish useful computation from a loop.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `get_cpu_history(container=None, minutes=30)` | Host or named-container series | `READ_ONLY_SAFE` |
| `get_host_cpu()` / `get_host_load()` | Busy %, CPU count, load and current pressure | `READ_ONLY_SAFE` |
| `get_container_resources(container)` | Current CPU and resource counters | `READ_ONLY_SAFE` |
| `get_top_cpu_processes(limit=10)` / `get_container_processes(container)` | Bounded ownership and process observations | `READ_ONLY_SENSITIVE` |
| `get_io_metrics()` | Device activity/current I/O pressure | `READ_ONLY_SAFE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Request/retry/computation context | `READ_ONLY_SENSITIVE` |
| `capture_diagnostic_snapshot(container)` | Pre-action evidence | `READ_ONLY_SENSITIVE` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_cpu_constraints(container)` returns effective quota/period, cpuset and version; `get_cpu_throttling_history(container, minutes)` exposes matching cgroup counter deltas/coverage; `get_service_traffic_history(service_id, minutes)` returns request/completion/queue trends. All `READ_ONLY_SAFE`. cAdvisor offers CPU usage/throttling metrics, but enabled collectors and exact labels must be verified. [cAdvisor metric catalogue](https://github.com/google/cadvisor/blob/master/docs/storage/prometheus.md)

## Diagnostic workflow

| Step | Action / reason | Interpretation / next step |
|---|---|---|
| 1 | CPU histories and impact: confirm sustained temporal overlap | Short peak/no impact → observe, not restart. Sustained impact → 2. |
| 2 | Host CPU/load/pressure and I/O | High load with I/O pressure and low CPU busy → RB-010. CPU contention → 3. |
| 3 | Compare container demand to effective quota/affinity and throttling | Throttled with host spare → H5; missing constraint tool leaves this open. Host busy across tenants → H6/H1. |
| 4 | Rank processes; align traffic/completions and logs | More work with proportional completion supports H1; high CPU with stalled progress supports H2/H4; high retries/concurrency supports H3. |
| 5 | Correlate deploy/query/job changes; preserve counterevidence | Single expensive query → DBA/RB-013; new code without causal evidence → RB-018 investigation, no automatic rollback. |
| 6 | Snapshot, owner-selected containment, then fresh checks | No evidence of useful versus harmful work → insufficient_evidence; avoid speculative kill/restart. |

## Decision tree

```text
high load -> CPU busy/pressure? no -> I/O or other wait
  yes -> quota throttling with host spare? yes -> budget/config investigation
         traffic and useful work rising? yes -> demand/capacity
         one process busy with no progress? -> loop/expensive-work hypotheses
         several competing workloads? -> host contention/concurrency
         evidence incomplete? -> abstain and request missing telemetry
```

## Evidence interpretation

Record whether a CPU value is host percent, percent of one core, or cores consumed; the current history helper's one-CPU label does not establish host normalization. CPU quota and affinity restrict available execution independently of visible host capacity. [Docker CPU constraints](https://docs.docker.com/engine/containers/resource_constraints/#cpu)

## False positives and edge cases

Counter resets, multicore values above 100% of one core, startup/compilation, short samples, process CPU averaged over lifetime, virtual-machine steal, shared host activity, changing quotas and a diagnostic probe itself adding load.

## Diagnosis outcome

Use all common outcomes. Probable cause needs demand/progress or throttling evidence plus counterevidence against I/O and host contention; otherwise record multiple hypotheses or insufficient evidence without labeling normal utilization a defect.

## Mitigation

Owner may reduce an identified non-critical workload/concurrency. Restart is not a general CPU remedy; a separately authorized single restart may recover an evidenced wedged process under an existing supported incident, never by falsifying this detector class.

## Recovery

Latency/completions recover and runnable/pressure/throttle evidence meets the service budget under representative load. Low CPU because requests disappeared is not recovery.

## Root-cause correction

Fix loops/algorithms, tune queries/concurrency, bound retries, allocate appropriate CPU quota or improve placement/capacity after profiling.

## Action safety

Stopping a producer, restarting a process or changing CPU allocation is `MUTATING_HIGH_RISK`. Require named owned workload/immutable ID, demand attribution, protected critical-service list, before/after settings, host reserve and one approved operation. Block absent CPU-change tool, unknown work loss, missing predicates or unsupported class/gate. The existing `change_resource_limit` changes memory only; it is not a CPU tool. No model kill/nice/scheduler interface is allowed.

## Human-in-the-Loop

Approval must show useful work lost/delayed, affected tenants, exact stop/restart/config change and rollback plan. Prose cannot turn an unsupported write into a capability; operator procedures remain outside Argus execution.

## Forbidden actions

`FORBIDDEN`: arbitrary process kill, disabling quotas globally, realtime-priority escalation, restarting all busy services, changing memory via a mislabeled CPU fix or scaling load into an exhausted host.

## Evidence preservation

Capture process ownership, CPU/quota/traffic windows and snapshot before any restart. Avoid expensive unbounded profiling during saturation; a missing safe profiler is a gap.

## Verification

Three source-fresh samples after the change, then 5 minutes of restored representative work: configured latency/completion targets, declining backlog, acceptable CPU pressure/throttling and stable error rate. Recurrence, missing workload telemetry or reduced traffic alone fails closure. Timeout escalates; no repeat restart.

## Rollback

Restarts cannot restore in-flight work. A configuration owner records previous quota/concurrency and capacity implications; rollback needs separate approval and must not reintroduce overload. No CPU rollback tool currently exists.

## Escalation

Application/performance owner for H2/H4, platform for H5/H6, DBA for expensive queries. Attach normalized time series, quota, progress evidence and missing observations. Stop at read budget or inability to attribute work safely.

## Recording / memory

Common record plus CPU units/denominator, effective budget, workload progress, victim/consumer distinction and remaining profiling task.

## Prevention / follow-up

Load-test CPU budgets, instrument queue/progress, optimize hot paths and retain throttle history and deployment fingerprints.

## Lab validation

Dedicated 2-vCPU VM: a disposable fixture runs two bounded busy-loop workers, one per CPU, for 120 seconds while an independently capped synthetic API measures latency. Use the shared 30-second lab pending duration; confirm actual CPU pressure/impact before expecting a trigger. Repeat with only the API capped to 0.25 CPU while the host has spare capacity, and with an I/O-bound fixture. Expect proposed/unsupported CPU trigger, RB-006, and H2/H5/RB-010 respectively when evidence supports them; otherwise record an inconclusive fixture. Assert no arbitrary kill, no misuse of memory-limit tool, denied approval → zero action. Operator stops only the injected fixture; verify representative API work and pressure for 5 minutes and retain detection→record artifacts. Stale throttle data must preserve uncertainty. Not executed.

## References

- [Linux load average](https://man7.org/linux/man-pages/man5/proc_loadavg.5.html), [Docker CPU constraints](https://docs.docker.com/engine/containers/resource_constraints/#cpu).
- [cAdvisor metrics](https://github.com/google/cadvisor/blob/master/docs/storage/prometheus.md), [kernel PSI](https://docs.kernel.org/accounting/psi.html).

## Argus capability gaps

### Missing telemetry

Effective CPU budget, throttle history, demand/progress and known healthy latency baseline.

### Missing tools

`get_cpu_constraints`, `get_cpu_throttling_history`, `get_service_traffic_history`.

### Tool improvements

Unambiguous CPU normalization, real sample timestamps, interval-based process CPU and identity-scoped histories.

### Detector improvements

Separate host contention from quota throttling; implement a detector and matching alert; avoid load-only diagnosis.
