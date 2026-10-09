# RB-010 — Disk I/O saturation

## Metadata

```yaml
id: RB-010
title: Disk I/O saturation
status: draft
owner: Argus Team
version: 1.0.1
created: 2026-09-29
last_reviewed: 2026-10-09
source_review_date: 2026-09-29
last_tested: null
detector: disk_io_saturation
```

## Scope

Linux block storage serving declared Docker/host workloads. Record device→mount→workload mapping, kernel, storage type, virtualization and device limits. Remote/network storage needs its own provider telemetry. Capacity shortage is RB-005, database-specific storage RB-019. Apply [shared contracts](../RUNBOOK-CONVENTIONS.md); no I/O detector is implemented.

## Incident definition

Storage service time/backlog limits useful workload progress. Used disk bytes and disk performance are different dimensions. Kernel disk statistics include cumulative counters and instantaneous in-flight counts; resets must be handled when deriving rates. [Kernel I/O statistics](https://docs.kernel.org/admin-guide/iostats.html)

## User / service impact

Observe slow requests, commits, file operations and stalled queues. A busy device doing useful background work without degradation need not be an incident.

## Trigger / detection conditions

Proposed selection: storage latency or I/O pressure exceeds a calibrated device baseline for 5 minutes with service degradation. Do not use universal “100% utilization” as a standalone capacity diagnosis. Require device identity, three distinct samples and nonzero operations before latency-per-operation ratios. Stale/reset counters and missing PSI are unknown.

## Symptoms

Elevated I/O stall, long operation times, queue buildup, high device activity, slow DB/application writes or high load with limited CPU work.

## Plausible causes / hypotheses

H1 legitimate write/read-heavy demand; H2 log storm; H3 database query/checkpoint workload; H4 image pull/build; H5 swap pressure; H6 storage degradation/throttling; H7 constrained container I/O budget; H8 filesystem full rather than slow.

## Required evidence

Time-aligned per-device operation/latency/queue data, workload attribution, I/O pressure, memory/swap, filesystem availability, block limits, application latency and errors. Container block-byte counters alone do not establish latency or ownership of all buffered writeback.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `get_io_metrics()` | One-second device rates/utilization and current I/O pressure | `READ_ONLY_SAFE` |
| `get_disk_usage(path=None)` | Rule in/out capacity/inode shortage | `READ_ONLY_SAFE` |
| `get_host_memory()` / `get_host_load()` | Memory pressure and host contention context | `READ_ONLY_SAFE` |
| `get_container_resources(container)` | Related block-I/O counters and resource snapshot | `READ_ONLY_SAFE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Timed workload/write errors | `READ_ONLY_SENSITIVE` |
| `inspect_database_health(container)` | DB wait/transaction hints if involved | `READ_ONLY_SENSITIVE` |
| `correlate_incident_timeline(container, minutes=30)` | Workload and failure chronology | `READ_ONLY_SENSITIVE` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_io_history(device_id, minutes)` for operation rates, latency, queue and pressure with reset/coverage metadata, `READ_ONLY_SAFE`; `get_storage_topology(host_id)` maps approved mounts/devices/containers, `READ_ONLY_SENSITIVE`; `get_storage_health(device_id)` provides sanitized device/provider errors and limits, `READ_ONLY_SENSITIVE`. `get_disk_history` measures root space consumption, not I/O performance.

## Diagnostic workflow

| Step | Action / why | Interpretation / next step |
|---|---|---|
| 1 | Identify affected mount/device and verify service latency | Unknown mapping → request topology; do not attribute busiest unrelated device. |
| 2 | Disk capacity/inodes and I/O snapshot/history | Capacity shortage → RB-005. Sustained performance pressure → 3; single busy second insufficient. |
| 3 | Memory/pressure versus device history | Swap/host memory pressure precedes I/O → RB-007/H5. Otherwise 4. |
| 4 | Relate declared workload counters/logs/change times | Build/log/DB demand leads slowdown → H2/H3/H4 candidates. Buffered/shared-device ambiguity remains explicit. |
| 5 | Storage health/budget evidence | Errors or imposed throughput limits → H6/H7; absent evidence cannot prove hardware failure. |
| 6 | Preserve evidence, choose narrow producer containment and verify | Stop non-critical producer only through its accepted procedure; unknown/critical owner escalates. |

## Decision tree

```text
space/inodes exhausted? -> RB-005
  no -> same-device latency/pressure sustained?
          no -> transient or wrong bottleneck
          yes -> swap? -> RB-007
                 known workload growth? -> log/build/DB owner
                 device errors/limits? -> storage owner
                 attribution missing? -> insufficient_evidence
```

## Evidence interpretation

I/O timing/utilization depends on device concurrency and counter semantics; use workload latency, pressure and baseline together. Dividing time counters by operations needs matching windows and reset handling. PSI is contention evidence, not a hardware-failure diagnosis. [Kernel I/O statistics](https://docs.kernel.org/admin-guide/iostats.html), [PSI](https://docs.kernel.org/accounting/psi.html)

## False positives and edge cases

Parallel NVMe/RAID devices, double-counted partition/device counters, buffered writes, burst credits, remote storage, zero-operation denominators, boot resets, cold caches and diagnostic scans adding load.

## Diagnosis outcome

All common outcomes permitted. Probable cause needs same-device timing, workload or fault evidence and counterevidence against memory/capacity; a busy disk alone yields an unresolved bottleneck hypothesis.

## Mitigation

Operator defers a proven non-critical build/batch/log producer or reduces concurrency. No cleanup merely to improve latency, and no automatic DB restart. Preserve transaction durability.

## Recovery

Storage operation latency/pressure and service completion return to target under representative work, with backlog draining and no device errors.

## Root-cause correction

Optimize queries/write amplification, bound logs/build concurrency, fix swap pressure, provision appropriate storage, or repair degraded devices through the storage owner's procedure.

## Action safety

Producer stop, scheduling/storage/config changes are `MUTATING_HIGH_RISK`. Require exact owner/target, mapped device, safe work-loss budget, protected DB/control-plane resources, current reserve and rollback. Block unknown shared-device users, absent capability/policy, unverified degradation or unavailable audit. No automatic storage-admin capability exists.

## Human-in-the-Loop

Show which producer will be paused, impact on queued work and other device users, exact arguments, expected relief and verification target. An approval does not authorize arbitrary I/O scheduler or database tuning.

## Forbidden actions

`FORBIDDEN`: disable fsync/durability, drop caches globally, run unbounded benchmarks on production storage, delete data for a latency symptom, arbitrary kill or device reset.

## Evidence preservation

Preserve compact device/window metrics and redacted workload fingerprints remotely; avoid recursive scans/core dumps during I/O distress. State incomplete device mappings explicitly.

## Verification

Three fresh source observations after the intervention and 10 minutes of comparable load: latency/pressure within calibrated baseline, queues drain, critical writes succeed and errors do not recur. Idle workload alone is not recovery. Stale device metrics, renewed stalls or insufficient verification time escalates.

## Rollback

Resume paused work only after reserve and pacing review. Storage/config owner retains previous settings, but does not restore known overload. No automatic disk configuration rollback or transaction undo is available.

## Escalation

Storage/platform owner for faults/unknown mapping, DBA for database demand, application owner for logging. Attach device/consumer mapping, before/after performance, error evidence and unresolved alternatives. Stop after ineffective containment.

## Recording / memory

Common record plus device topology, kernel/metric semantics, operation denominators, consumer attribution, pressure/latency baseline and postponed work.

## Prevention / follow-up

Device-specific latency/queue alerts, historical I/O/PSI, workload budgets, build isolation and capacity tests on disposable storage.

## Lab validation

Dedicated disposable data disk: operator runs a 120-second capped write fixture with a 128 MiB file and a 20 MiB/s ceiling while a synthetic reader measures latency; root disk and production volumes are excluded. Choose limits that demonstrably affect the test disk, else record no incident. Expect proposed/unsupported RB-010 trigger and demand attribution, not disk-full diagnosis. Deny a request to disable durability; no Argus write. Operator stops only the fixture and verifies workload latency/pressure for 10 minutes. Repeat a full-filesystem fixture to require RB-005 routing; capture detection through recording. Not executed.

## References

- [Kernel I/O statistics](https://docs.kernel.org/admin-guide/iostats.html), [kernel PSI](https://docs.kernel.org/accounting/psi.html).
- [Node Exporter collectors](https://github.com/prometheus/node_exporter) — available collector families must be checked in deployment.

## Argus capability gaps

### Missing telemetry

Historical performance/queues, workload-device mapping, storage error/budget evidence.

### Missing tools

`get_io_history`, `get_storage_topology`, `get_storage_health`.

### Tool improvements

Reset-aware rates, latency/queue fields, device identity and explicit short-sample limitations.

### Detector improvements

Implement performance-plus-impact selection separately from disk-capacity detection.
