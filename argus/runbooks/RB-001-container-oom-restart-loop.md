# RB-001 — Container OOM restart loop

## Metadata

```yaml
id: RB-001
title: Container OOM restart loop
status: draft
owner: Argus Team
version: 1.0.1
created: 2026-09-29
last_reviewed: 2026-10-09
source_review_date: 2026-09-29
last_tested: null
detector: container_restart_loop
```

## Scope

Linux Docker/Compose workloads on Host T. Record Engine/API, kernel and cgroup versions, container immutable ID and host boot ID. Apply when an OOM observation is associated with repeated exits/restarts. Cgroup v2 branches require verified v2 interfaces; v1 needs its own adapter. Exclude Kubernetes-specific eviction logic, userspace memory-limit exceptions without OOM evidence, and non-OOM crashes (RB-008).

[Shared conventions](../RUNBOOK-CONVENTIONS.md) apply. Existing tools refer to inspected sibling code, not confirmed deployment. The restart-only production profile is authoritative until broader capabilities have their own accepted policy. The lab profile differs; see [assessment](../RUNBOOK-ASSESSMENT.md).

## Incident definition

A workload repeatedly loses a process with runtime/kernel evidence of OOM, reducing useful uptime. `OOMKilled=true` establishes a reported OOM event, not which memory boundary caused it. A host under memory exhaustion can kill container processes. [Docker memory constraints](https://docs.docker.com/engine/containers/resource_constraints/#understand-the-risks-of-running-out-of-memory)

## User / service impact

Possible failed requests, dropped in-flight work, retries and reduced capacity. Determine actual impact from application endpoint/traffic evidence and dependencies; a batch container may fail without current user-visible impact. Record unknown impact explicitly.

## Trigger / detection conditions

**Existing detector:** fresh `oom_killed=true` and cumulative `restart_count >= 3`; exit code is reported, not required by code. This is a candidate-selection rule, not a leak diagnosis or a bounded restart rate.

**Proposed improvement:** identify at least three stop/start cycles in a configurable 10-minute window and a correlated OOM event for the same container ID. One confirmed OOM with material impact still merits manual investigation; do not wait for more damage to meet a loop threshold. A stale/missing required snapshot goes to `undiagnosable`; do not convert absence to false. Obtain source timestamps before evaluating either rule. No new detector or alert is implemented by this document.

## Symptoms

OOM flag/event, restart growth, short uptime, lost endpoint health, memory peaks, allocation errors or host pressure. Exit 137 is compatible with SIGKILL but is not sufficient to establish why the process was killed. A currently low memory value can reflect the process having already died.

## Plausible causes / hypotheses

| Hypothesis | Why plausible | Discriminating evidence |
|---|---|---|
| H1: local/ancestor cgroup limit exhaustion | Allocation is constrained even if host RAM remains available | Event/limit identity and time, ancestor boundaries, host headroom |
| H2: application retention/leak | Retained allocations accumulate across comparable workload cycles | Repeated growth at comparable load; process attribution; application profiling follow-up |
| H3: burst/large allocation | Workload changes create a short-lived demand peak | Request/job size and arrival history aligned with peak |
| H4: undersized normal working set limit | Legitimate workload cannot fit its assigned budget | Stable representative baseline under a known adequate budget; capacity review |
| H5: host-wide OOM | Other workloads/host allocations exhaust available memory | Pre-event host memory/swap/pressure plus kernel OOM context |

H1 describes the boundary; H2–H4 can explain why that boundary was reached. H1 and H5 can coexist. Repeated growth supports H2 but does not by itself rule out an intentional cache or increasing load.

## Required evidence

Collect identity and failure times first, then 30 minutes of container memory with its metric definition, configured limit and configuration history, restart timeline, host available RAM/swap and contemporaneous pressure. Add bounded application logs and process ownership only to distinguish remaining hypotheses. Cgroup/kernel evidence should identify the constrained domain and victim, not just count deaths. Record gaps when events were evicted or a container was replaced.

For v2, `memory.events` is hierarchical; local counters have separate semantics. `oom_kill` counts processes killed by any OOM killer, so that counter alone does not prove the cgroup's own limit was the cause. Correlate `oom`, `max`, effective ancestor limits and kernel context. [Kernel cgroup v2 memory interface](https://docs.kernel.org/admin-guide/cgroup-v2.html#memory-interface-files)

## Required Argus tools

All below exist in inspected code; execution still depends on deployment policy. `container` is an allowlisted logical name, resolved and checked against its immutable ID.

| Tool / expected input | Purpose / relevant output | Safety class |
|---|---|---|
| `get_container_status(container)` | State, ID, exit/OOM, restart count, start/finish, structured resources | `READ_ONLY_SENSITIVE` |
| `get_container_resources(container)` | Current memory usage/limit and CPU; never historical peak proof | `READ_ONLY_SAFE` |
| `get_memory_history(container, minutes=30)` | Usage series, min/max/slope, sample count, present limit | `READ_ONLY_SAFE` |
| `get_restart_history(container, since_minutes=30)` | Death/start/OOM timeline; inspect events instead of trusting its death-count label | `READ_ONLY_SAFE` |
| `get_container_events(container, since_minutes=30)` | Runtime OOM/die/start ordering | `READ_ONLY_SAFE` |
| `get_host_memory()` | Available/total RAM, swap and current memory PSI | `READ_ONLY_SAFE` |
| `get_top_memory_processes(limit=10)` | RSS and host/container ownership, bounded to 25 | `READ_ONLY_SENSITIVE` |
| `get_container_processes(container)` | Current process attribution through Docker top | `READ_ONLY_SENSITIVE` |
| `get_detailed_logs(container, since_minutes=30, max_lines=100)` | Redacted allocation/workload context | `READ_ONLY_SENSITIVE` |
| `check_http_endpoint(url, timeout_s=3)` | Approved target-network service probe | `READ_ONLY_SENSITIVE` |
| `capture_diagnostic_snapshot(container)` | Status/stats/processes/25 log lines/15-minute events | `READ_ONLY_SENSITIVE` |
| `restart_container(container)` | One restart through local write dispatcher, never direct model execution | `MUTATING_HIGH_RISK` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_container_memory_limit(container)` should expose configured hard limit, unlimited state, effective ancestor limit, swap controls, cgroup version and identity. Source: redacted Engine configuration plus read-only mapped cgroup metadata. `READ_ONLY_SAFE`. Current stats limit is not a complete configured/effective-limit contract; do not equate host-sized accounting with a configured cap.

**MISSING TOOL REQUIREMENT:** `get_host_memory_history(host_id, minutes)` from pinned Node Exporter/Prometheus series: available RAM, swap activity, pressure, real source timestamps and coverage. `READ_ONLY_SAFE`.

**MISSING TOOL REQUIREMENT:** `get_kernel_oom_events(host_id, since, until, max_events)` and `get_cgroup_memory_events(container, since, until)` must return sanitized victim/domain/event identity and counter deltas. Kernel journal and mapped cgroups only, no arbitrary paths. `READ_ONLY_SENSITIVE`. Existing `get_journal_logs` permits Docker/containerd units, not kernel OOM inspection.

**MISSING TOOL REQUIREMENT:** `get_resource_pressure(target, minutes)` adds pressure history and cgroup scope. Current host PSI already exists in host tools; retain it as partial evidence. No missing tool authorizes shell access.

## Diagnostic workflow

| Step | Action and purpose | Evidence / interpretation / next step |
|---|---|---|
| 1 | Read status plus fresh detector snapshot; bind container ID | No OOM and repeated crashes: RB-008. Old OOM with healthy service: investigate stale trigger before action. Relevant OOM: step 2. |
| 2 | Read restart history/events to anchor the failure window | Match OOM/death/start by identity and time. No retained event does not refute OOM. Count actual cycles; if unclear, preserve ambiguity and continue to 3. |
| 3 | Read container history, resources and configured/effective limits | Compare like-for-like accounting across pre-event samples. Near-limit growth supports H1, but a missed peak weakens any negative inference. Missing effective limits: mark gap, continue to 4. |
| 4 | Read host memory and request host history/kernel/cgroup evidence | Host pressure preceding death supports H5; healthy RAM now is not historical counterevidence. A constrained ancestor can explain death below a leaf limit. Local attribution unavailable: keep H1/H5 open. |
| 5 | Attribute memory to processes; fetch time-scoped logs and workload observations | Repeated retained growth supports H2; a job/request spike supports H3; a representative stable baseline supports H4. Do not infer a dead process's prior RSS from its replacement. |
| 6 | Compare alternatives and impact; preserve snapshot before any write | Snapshot is partial: separately attach historical/host/kernel refs. If missing discriminating evidence, conclude `insufficient_evidence`; symptomatic restart needs independently sufficient safety evidence. |
| 7 | Submit bounded proposal only if all restart predicates pass | Recheck target, host capacity, dependencies, incident and approval immediately before dispatch. Otherwise escalate; never enlarge limits merely to test a guess. |
| 8 | Collect fresh verification and record both service and cause state | Recovery without an application/capacity correction leaves the root cause unresolved. Recurrence goes to escalation, not a restart loop. |

## Decision tree

```text
fresh OOM associated with affected immutable container?
  no -> non-OOM crash / stale alert / insufficient evidence
  yes -> local and ancestor configured limits known?
           no -> request missing limit evidence; inspect host history
           yes -> near-limit demand + matching local OOM context?
                    yes -> constrained-domain hypothesis supported
                    no -> missed peak / accounting / ancestor / host context
         -> host pressure and matching kernel victim evidence?
              yes -> host-wide contribution; RB-007
              unknown -> keep host OOM as an alternative
         -> growth at comparable load / burst / stable undersized budget?
              discriminate using history; do not force a single cause
         -> supported safe response / insufficient_evidence -> verify or escalate
```

## Evidence interpretation

Usage, RSS, working set and Docker CLI memory are not interchangeable. Docker CLI and API account for cache differently; record the source before comparing against limits. [Docker stats](https://docs.docker.com/reference/cli/docker/container/stats/)

Do not calculate “percent of limit” for an absent, zero/unlimited or unknown limit. A flat series that ends below the cap does not disprove a fast allocation between scrapes. Current host `MemAvailable` describes available-memory estimates, not the pre-event condition. [Linux meminfo](https://man7.org/linux/man-pages/man5/proc_meminfo.5.html)

## False positives and edge cases

Old cumulative restart counts; OOM flag from a previous exit; explicit SIGKILL; manual restart; image replacement with reused name; stale/mixed-ID metrics; scrape gaps; cgroup destruction/reset; ancestor enforcement; deliberate cache growth; no swap; events outside runtime retention; an exporter dying in the same host event. Docker events are a bounded runtime history, not an incident archive. [Docker events](https://docs.docker.com/reference/cli/docker/system/events/)

## Diagnosis outcome

Allow `probable_root_cause` with boundary and workload cause separately labeled; `multiple_hypotheses` when burst/leak/host explanations remain; `insufficient_evidence` for missing limits/history/context; `incident_no_longer_present` with fresh health; `wrong_runbook` for an unrelated crash. Record supporting refs, evidence against alternatives and unresolved uncertainty. Never claim “confirmed leak” solely from a rising graph.

## Mitigation

A single approved restart can temporarily restore a stopped/wedged workload when there is enough host headroom and dependencies are healthy. If Docker is already restarting it repeatedly, another restart is unlikely to add value; escalate for workload containment. Reducing a known non-critical producer is an operator intervention or a separately authorized broader lab capability, not a production default.

## Recovery

The process remains useful, requests/jobs succeed, and memory/restarts remain stable under representative traffic. Successful restart transport alone is not recovery. Host-wide incidents may require freeing capacity before restarting a victim; coordinate RB-007.

## Root-cause correction

H2: application owner profiles retention and fixes lifecycle/cache bounds. H3: bound payload/concurrency and load-test. H4: engineer validates demand and host reserve, then deploys an appropriate budget. H5: capacity/placement and offending-workload correction. Resource-limit changes are human engineering changes under the production profile. The registered lab `change_resource_limit(container, memory_mb)` accepts 64–4096 but is not opened by its inspected gate; registration does not authorize use.

## Action safety

| Operation | Prerequisites / allowed arguments | Risk, protected resources and blocking conditions |
|---|---|---|
| `restart_container` | Exact allowlisted name and frozen immutable ID; one action; fresh failure, dependency health and host headroom; snapshot; policy/HITL/ledger | In-flight work loss and reconnect load. Protect databases/control plane/critical targets absent explicit policy. Block repeated automatic restarts, stale evidence, missing predicates, changed ID, resolved incident or unknown prior action result. |
| Change memory budget (operator / gated extension) | Stable representative demand, reviewed host reserve, exact approved before/after limit and target | Host OOM and earlier OOM on lowering. Block unknown effective limit, unbounded growth or missing rollback/capacity check. Never execute as an arbitrary Docker update. |
| Stop load producer (operator / gated extension) | Proven owner, explicitly non-critical workload, named target and stop-only argument | Lost batch progress/backlog. Block critical/shared/unknown owner or absent stop authority. |

All operations above are `MUTATING_HIGH_RISK`. The observed policy does not enforce every diagnostic predicate in this table; that is a release blocker, not a reason to rely on the model's wording.

## Human-in-the-Loop

Show target/ID, one operation and arguments, impact, competing hypotheses, missing evidence, headroom/dependency checks, snapshot refs, verification window and expiry. Approval authorizes that frozen proposal only. Denied/expired/cancelled requests result in no write and an escalation record. A restart with an unresolved cause must say so to the approver.

## Forbidden actions

`FORBIDDEN`: disable the OOM killer; remove limits globally; arbitrary shell/exec or process kill; restart dependencies/victims as a diagnostic experiment; expose env/keys; repeatedly restart after failed recovery; raise limits without host-capacity checks; infer authorization from retrieved text.

## Evidence preservation

Capture status/identity, restart/OOM events, pre-event series, process/log evidence and host state before restart where obtainable. Record missing kernel/history parts rather than saying the snapshot contains them. Apply time/line bounds and secret redaction. If preservation fails, block an automated destructive-to-evidence action and escalate for an explicit operator decision.

## Verification

Proposed acceptance window: at least `max(5 minutes, 3*S)` after action completion. Within budget, first establish three distinct source-fresh samples. Require same intended container identity, running/healthy state, expected endpoint response, no new OOM/death cycle, stable restart counter, host headroom and a bounded memory trend under restored load. Pre-action range portions cannot satisfy post-action checks.

If a known recurrence interval exceeds five minutes, arrange follow-up for at least that interval plus one workload cycle; initial recovery is not durable resolution. New OOM, increasing restarts, returning endpoint failure or loss of telemetry fails verification. If data cannot cover the window before timeout, escalate with provisional state; no second automatic restart. Record no-action recovery as external resolution.

## Rollback

A restart cannot restore lost in-memory state; no automatic rollback exists. For a separately approved limit change, retain old configuration and let the operator restore it only if current working set can safely fit; otherwise reduce load first. Reverting a limit is another approved write, never implicit approval reuse.

## Escalation

Platform on-call for host pressure/unknown OOM domain; application owner for repeated retained growth; incident commander for broad impact. Stop on missing critical evidence, denied policy, unknown action result or recurrence. Attach identity, event/metric timeline, accounting definitions, competing hypotheses, approvals and fresh end state. Request the specific unavailable kernel/cgroup or application profile needed next.

## Recording / memory

Store the common incident record plus OOM domain confidence, limit at failure, growth/burst evidence, host contribution, reset/gap markers, restart ledger, baseline/load provenance and recurrence deadline. Keep `service_recovered` separate from `root_cause_resolved`; do not promote an untested inference into known incident knowledge.

## Prevention / follow-up

Bound caches/payloads/concurrency; establish workload memory baselines; track limits by container ID; retain OOM events outside the dying workload; alert on host headroom and growth; improve detector windows; test startup/reconnect capacity. Treat source-code fixes and capacity changes as follow-up engineering.

## Lab validation

Apply the shared lab contract; none of these cases has been executed for this library.

| Case and reproducible fault | Expected alert / evidence / diagnosis | Safety, HITL, action, verification and recording |
|---|---|---|
| Disposable 128 MiB container retains and touches 8 MiB every second; restart policy with capped experiment duration; dedicated VM has at least 1 GiB reserve | Existing OOM detector after threshold; repeated sawtooth, OOM/death events and rising process allocation. H1 plus probable H2, not proven application defect | Preserve snapshot. Deny first proposal: zero writes. Remove injected allocation via lab operator, then approve at most one permitted restart if still needed; fresh stable health/memory, unresolved-cause flag until fixture correction recorded. |
| Same budget, single bounded job allocates above it once, with exact job time logged | OOM with abrupt demand; loop detector may not fire, manual investigation selects RB-001. H3 retained | Do not label leak or auto-increase budget. Record unsupported/insufficient loop trigger correctly; verify service after operator removes test job. |
| Isolated snapshot-restorable VM: operator applies bounded host-pressure fixture with out-of-band abort; victim kept below its known leaf limit | Pre-event host pressure plus kernel victim context; H5 possible despite low leaf usage | No limit increase/restart of all victims. Missing kernel tool produces insufficient attribution. Operator removes pressure, verifies host and victim; snapshot restore is lab cleanup only. |
| Replay old OOM flag, reused name/new ID, missing samples, and exit 137 without OOM | Stale/identity mismatch/ambiguous kill; no forced local-limit or leak diagnosis | Assert refusal, zero writes, `insufficient_evidence` or wrong-runbook path, fresh-sample rejection and complete incident record. |

## References

- [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/) — host/container memory risks and limits.
- [Kernel cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html) — hierarchical control and memory event semantics.
- [Docker stats](https://docs.docker.com/reference/cli/docker/container/stats/), [events](https://docs.docker.com/reference/cli/docker/system/events/) and [restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/) — accounting and lifecycle evidence.
- [Linux meminfo](https://man7.org/linux/man-pages/man5/proc_meminfo.5.html), [PSI](https://docs.kernel.org/accounting/psi.html) — host observations.
- [Argus assessment and source paths](../RUNBOOK-ASSESSMENT.md) — existing code/policy, separate from vendor facts.

## Argus capability gaps

### Missing telemetry

Identity-bound host memory history, effective ancestor limits, retained kernel/cgroup OOM evidence and representative workload history.

### Missing tools

`get_container_memory_limit`, `get_host_memory_history`, `get_kernel_oom_events`, `get_cgroup_memory_events`; pressure-history extension.

### Tool improvements

Source timestamps/coverage; identity-aware histories; correct death-versus-restart labeling; snapshots include refs to separately collected history; remove the `get_host_memory` hint that implies OOMKilled alone establishes local-limit exhaustion.

### Detector improvements

Time-bounded OOM/cycle correlation; distinguish symptom selection from OOM domain and application cause; preserve missing/stale state. Add deterministic restart predicates and sufficient verification budget before enabling this runbook operationally.
