# RB-007 — Host memory pressure

## Metadata

```yaml
id: RB-007
title: Host memory pressure
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

Linux Host T RAM, swap, host processes and containers. Record kernel/cgroup/PSI availability, boot ID, physical memory and enabled swap. Exclude isolated container-limit exhaustion with adequate host reserve (RB-001). Follow [common contracts](../RUNBOOK-CONVENTIONS.md); no host-memory detector is implemented.

## Incident definition

Host allocation/reclaim pressure compromises workload progress or threatens OOM. Low `MemFree` alone is insufficient: `MemAvailable` estimates memory usable for new applications without swapping. [Linux meminfo](https://man7.org/linux/man-pages/man5/proc_meminfo.5.html) PSI measures time tasks are stalled by resource contention, not bytes used. [Kernel PSI](https://docs.kernel.org/accounting/psi.html)

## User / service impact

Possible latency, swap-related I/O, stalled processes and killed workloads across services, including monitoring. Measure affected endpoints/jobs; a healthy surviving service does not establish host-wide health.

## Trigger / detection conditions

Proposed alert: available RAM below 10% for 5 minutes with sustained memory pressure or workload degradation; immediate investigation on kernel OOM with impact. Pressure threshold must be calibrated to host baseline and PSI support. No-swap is configuration, not automatic failure. Required sample loss selects undiagnosable/observability escalation, not zero pressure.

## Symptoms

Declining available RAM, reclaim stalls, swap activity, increased I/O latency, multiple OOM victims, failed allocations and missing exporters.

## Plausible causes / hypotheses

H1 one runaway container; H2 aggregate legitimate containers exceed capacity; H3 host process growth; H4 kernel/cache/shared-memory pressure; H5 burst workload; H6 sustained leak; H7 swap/storage impairment amplifies memory stalls. A killed container can be a victim of another consumer.

## Required evidence

Pre-incident and current available RAM/swap/pressure, per-consumer memory trend, host/process ownership, kernel victim/domain records, representative load, I/O context and recent placement/budget changes. Process RSS totals can double-count shared mappings and omit other allocations; do not force them to equal host use.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `get_host_memory()` | Current available/total RAM, swap and memory pressure | `READ_ONLY_SAFE` |
| `get_top_memory_processes(limit=10)` | Bounded RSS ranking and ownership | `READ_ONLY_SENSITIVE` |
| `get_container_list()` | Known workloads and states | `READ_ONLY_SENSITIVE` |
| `get_container_resources(container)` / `get_memory_history(container, minutes=30)` | Consumer usage and trend | `READ_ONLY_SAFE` |
| `get_io_metrics()` | I/O rates/pressure for swap-related alternative | `READ_ONLY_SAFE` |
| `get_container_events(container, since_minutes=30)` | Victim lifecycle chronology | `READ_ONLY_SAFE` |
| `capture_diagnostic_snapshot(container)` | Preserve suspected consumer/victim state | `READ_ONLY_SENSITIVE` |

Limit investigation to declared related workloads and configured read budgets; do not inventory every process/filesystem unrestrictedly.

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_host_memory_history(host_id, minutes)` and pressure/swap-activity history, `READ_ONLY_SAFE`; `get_kernel_oom_events(host_id, since, until, max_events)`, `READ_ONLY_SENSITIVE`. These reuse RB-001 contracts. **MISSING TOOL REQUIREMENT:** bounded host-memory category/placement history and effective cgroup budgets, not arbitrary `/proc` reads. Current PSI is available; historical attribution is missing.

## Diagnostic workflow

| Step | Action / why | Interpret / next step |
|---|---|---|
| 1 | Fresh host memory plus impact | Cache-heavy but available RAM/pressure normal → investigate other failure. Sustained shortage → 2. |
| 2 | Request pre-event host/swap/PSI history | Pressure preceding victims supports host contribution. Only post-kill memory available → preserve attribution uncertainty. |
| 3 | Rank consumers and inspect related container trends | Single growing owner → H1/H6; broad stable growth with demand → H2; host process → H3; unexplained gap → H4. |
| 4 | Compare growth to workload and changed placement | Burst supports H5; repeated retained growth at comparable load supports leak hypothesis. No baseline → do not call it a leak. |
| 5 | Inspect kernel context and I/O | Match OOM domain/victim; severe swap I/O supports H7/RB-010. Container limit-only event routes to RB-001. |
| 6 | Snapshot, owner containment plan, then verify whole host and victims | Unknown owner/critical consumer → escalate, not kill the largest PID. |

## Decision tree

```text
host pressure supported? no -> local cgroup / cache / different incident
  yes -> one consumer? -> container or host owner + growth investigation
         aggregate demand? -> capacity/placement
         unexplained memory? -> bounded kernel/shared-memory evidence
         OOM victim identified? -> do not equate victim with offender
         safe non-critical containment available? -> owner/HITL; else escalate
```

## Evidence interpretation

Compare pre-failure time windows. RAM freed by a kill can mask the original host shortage. CPU/memory/I/O pressure are different signals; swap occupancy alone does not show current swap activity. Under cgroup v2 the killed processes and constrained domain require contextual interpretation; use RB-001 for that analysis.

## False positives and edge cases

Reclaimable cache, no swap by design, shared mappings, lost exporter, host reboot/reset, changed VM size, short-lived allocations, incomplete container inventory, protected kernel allocations and a victim gone before sampling.

## Diagnosis outcome

Allow all common outcomes with host contribution and offender identity separately qualified. `insufficient_evidence` is appropriate when only a victim's OOM or current memory is available; do not name an offender without ownership evidence.

## Mitigation

Platform owner can pause a proven non-critical workload or reduce accepted load under an approved procedure. Restarting several victims simultaneously may worsen demand and is not a default action.

## Recovery

Sustained host reserve and progress return, pressure falls, no new OOM occurs, and affected services recover under representative demand. A stopped workload remains a functionality reduction.

## Root-cause correction

Fix application retention, bound caches/concurrency, rebalance budgets/placement or add reviewed capacity. Distinguish workload correction from simply enlarging available memory.

## Action safety

Workload stop, restart, limit/capacity/swap change are `MUTATING_HIGH_RISK`. Exact owned target/ID, protected database/control-plane list, workload-loss assessment, before/after budget and host reserve are required. Block unknown owner, missing deterministic headroom checks, critical target without explicit policy, unsupported class or absent capability. Broad lab stops are not enabled for this class by implication. No low-risk host memory mutation is offered.

## Human-in-the-Loop

Show offending versus victim evidence, host and service impact, exact containment and reduced functionality, capacity risks and recovery plan. Each action requires a separate frozen proposal or owner change procedure; no approval for arbitrary memory reclamation.

## Forbidden actions

`FORBIDDEN`: disable OOM killer, kill largest PID blindly, mass restart, globally drop caches, disable swap under pressure, remove all limits, change kernel memory settings through shell or expose process secrets.

## Evidence preservation

Small bounded snapshots of implicated workloads plus remote host history/kernel refs; avoid memory-heavy dumps on an exhausted host. Missing evidence capture blocks automatic state-destroying remediation and prompts operator escalation.

## Verification

Three source-fresh host/service observations after intervention, then 10 minutes including representative demand. Proposed available-RAM reserve above 15%, calibrated to host needs; pressure near baseline, swap activity no longer increasing abnormally, no new OOM, victim endpoints healthy. Monitor disappearance fails verification. Recurrence or inability to cover the window within budget escalates.

## Rollback

Killed processes cannot regain lost work. Resuming a paused producer is separately approved after sufficient reserve/correction. Capacity/limit changes preserve prior values, but reverting into known shortage is blocked; operator handles rollback safely.

## Escalation

Platform on-call immediately for broad pressure/monitor loss, application owner for attributed growth. Attach pre-event history, consumer/victim mapping, cgroup uncertainty, protected workloads and requested next measurement. Unknown action state never triggers repeat action.

## Recording / memory

Common record plus boot ID, total/available memory, swap configuration/activity, category/ownership uncertainty, impacted services and recurrence horizon.

## Prevention / follow-up

Host reserve budgets, pressure/history collection independent of victims, per-workload limits, leak tests and placement accounting.

## Lab validation

Snapshot-restorable dedicated 2 GiB VM with out-of-band observer: operator uses a time-limited allocator, 64 MiB increments, hard 1.5 GiB fixture cap and abort when available RAM is below 15% or observer fails. First run normally targets pressure without OOM; an OOM variant requires a separately approved disposable-VM plan. Compare one growing container versus several bounded consumers. Expect proposed/unsupported host trigger, H1 versus H2 when evidence supports it; a victim-only replay must abstain. Denied containment → zero writes; operator removes only fixtures, verifies host and service recovery for 10 minutes and records all lifecycle stages. No host fault was executed.

## References

- [Linux meminfo](https://man7.org/linux/man-pages/man5/proc_meminfo.5.html), [kernel PSI](https://docs.kernel.org/accounting/psi.html).
- [RB-001](RB-001-container-oom-restart-loop.md) — OOM boundary interpretation and missing tool contracts.

## Argus capability gaps

### Missing telemetry

Host memory/swap/pressure history, kernel OOM context, placement and effective budgets.

### Missing tools

Shared host-memory/kernel/pressure-history contracts and bounded memory-category inspection.

### Tool improvements

Avoid inferring local OOM from victim flags; expose ownership/coverage uncertainty and source times.

### Detector improvements

Host pressure detector with impact and freshness, separate from container OOM; target-scope and containment policy extensions.
