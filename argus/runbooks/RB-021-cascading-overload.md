# RB-021 — Host/service overload and cascading failure

## Metadata

```yaml
id: RB-021
title: Host/service overload and cascading failure
status: draft
owner: Argus Team
version: 1.1.0
created: 2026-09-29
last_reviewed: 2026-09-29
source_review_date: 2026-09-29
last_tested: null
detector: null
activation_prerequisite: validated_core_runbooks_and_service_load_policies
```

## Scope

Declared multi-service request graphs on Host T with known criticality, dependency capacity and retry/queue behavior. This is an advanced design draft; do not activate until core resource/dependency runbooks and bounded load controls are validated. Record service versions, topology/config revision and clock confidence. [Shared contracts](../RUNBOOK-CONVENTIONS.md) apply.

## Incident definition

A local capacity/failure event propagates as retries, queueing or redirected load increase demand on other services, producing further failures. Simultaneous alerts alone do not prove a cascade. Overload can be amplified by retry behavior and loss of capacity. [Google SRE cascading failures](https://sre.google/sre-book/addressing-cascading-failures/)

## User / service impact

Map affected critical paths, accepted/successful work, dropped/delayed jobs and healthy capacity. State the current degraded mode and which request priorities or customer cohorts lose functionality; lower errors after shedding can conceal lost work. Establish incident coordination early when several owners are involved; maintain a single shared timeline and decisions. [SRE incident response](https://sre.google/workbook/incident-response/)

## Trigger / detection conditions

Proposed selection: two or more connected services breach their objectives during a 5-minute correlated window with evidence of shared resource/dependency pressure and increased retry/queue load. Existing Argus can produce individual health/dependency/OOM incidents only; do not collapse them into an invented executable class. Missing graph/clock/load evidence means a suspected cascade, not a confirmed root cause.

## Symptoms

Rising latency/errors, queue depth/age, retries greater than incoming work, dropped traffic, saturated resources, pool/connection exhaustion and many victim health failures.

## Plausible causes / hypotheses

H1 demand exceeds a shared dependency; H2 retry feedback loop; H3 capacity loss/failover overloads survivors; H4 unbounded queues/concurrency; H5 noisy neighbor/shared-host resource failure; H6 deployment/config mismatch; H7 unrelated simultaneous incidents or monitoring failure.

## Required evidence

Versioned dependency graph, per-service golden signals, offered/admitted/completed/retried/dropped rates by approved priority/cohort, queue depth/age, dependency capacity, resource pressure and aligned event times. Record the active degradation policy, rejection behavior and remaining useful capacity. Identify feedback edges and victim/consumer roles. Recovering the “first alert” is not necessarily the highest-value containment.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `trace_request_path(container)` | Declared path checks, limited to actual topology | `READ_ONLY_SENSITIVE` |
| `correlate_incident_timeline(container, minutes=30)` | Related event chronology with missing-data limits | `READ_ONLY_SENSITIVE` |
| `get_cpu_history(container, minutes=30)` / `get_memory_history(container, minutes=30)` | Resource contribution | `READ_ONLY_SAFE` |
| `get_host_memory()` / `get_io_metrics()` | Shared-host contention | `READ_ONLY_SAFE` |
| `inspect_database_health(container)` / `get_db_connection_history(database, minutes=30)` | Shared database capacity | `READ_ONLY_SENSITIVE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Bounded retry/timeout evidence | `READ_ONLY_SENSITIVE` |
| `capture_diagnostic_snapshot(container)` | Selected implicated workload before intervention | `READ_ONLY_SENSITIVE` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_service_traffic_history(service_id, minutes)` distinguishes incoming/retried/completed/dropped work; `get_queue_health(service_id, queue_id, minutes)` returns depth, age, in-flight and drain rate; `get_retry_policy(service_id)` returns safe retry/timeout/concurrency metadata; `get_dependency_capacity(dependency_id)` reports tested budget/current admission. Traffic/queue/capacity are `READ_ONLY_SAFE`, config `READ_ONLY_SENSITIVE`. Bounded traffic shedding/concurrency controls would require separately reviewed write capabilities; none is presumed.

## Diagnostic workflow

| Step | Action / purpose | Interpret / next step |
|---|---|---|
| 1 | Establish topology, clock quality and critical-path impact | Incomplete graph/time ordering → preserve uncertainty. Monitoring gap → RB-014. |
| 2 | Align per-service demand/completion and resource/dependency data | Shared saturation preceding victims supports H1/H5; unrelated failures leave H7 open. |
| 3 | Compare offered versus retried work and queue age | Retry multiplication supports H2; rising old backlog without completion supports H4. Missing rate denominators prevents amplification claim. |
| 4 | Review capacity loss/failover/deploy changes | H3/H6 candidates; compare surviving capacity and demand, not just restart order. |
| 5 | Use validated core runbook to identify one narrow intervention | Choose a proven non-critical source/load control with expected measurable relief; protect victim services and required capacity. |
| 6 | Coordinator approves one bounded owner action and observes graph response | If response contradicts hypothesis, stop further changes and reassess; do not launch parallel speculative mitigations. |
| 7 | Gradually restore accepted work under owner supervision | Verify queue drain and all critical paths; keep unresolved defect follow-up. |

## Decision tree

```text
connected multi-service degradation + credible telemetry?
  no -> separate incidents / observability / insufficient_evidence
  yes -> shared capacity deficit? -> resource/dependency runbook
         retries amplify demand? -> bounded retry/load-control owner
         queues grow without useful completion? -> concurrency/backpressure owner
         capacity loss or bad release? -> recovery/compatibility owner
         narrow measured intervention unavailable? -> coordinated escalation
```

## Evidence interpretation

Admission control and bounded load shedding can protect useful work under overload, but the service must define priorities and rejection behavior in advance. Increasing timeouts or blindly adding retries can retain work and amplify pressure. These are design recommendations, not automatically safe runtime edits. [Google SRE handling overload](https://sre.google/sre-book/handling-overload/)

## False positives and edge cases

Common monitoring outage, clock skew, shared deploy, failover warmup, duplicate alerts, legitimate queued batch work, low traffic masking broken service, retries missing from metrics and graph edges absent from topology.

## Diagnosis outcome

All common outcomes allowed. Probable cascade needs supported propagation mechanism and affected edges, not just temporal correlation. State uncertainty about the initial defect separately from a well-supported harmful feedback loop.

## Mitigation

Incident coordinator directs one bounded reduction of non-critical demand/retries or pauses an attributed producer, using a pretested owner procedure with defined priority and rejection semantics. Measure accepted and shed work by priority/cohort and announce the degraded mode through the authorized incident process. Protect healthy capacity; mass restart and uncontrolled scale-out can worsen the incident. Core runbook gates still apply.

## Recovery

Critical good throughput returns, latency/errors meet objectives, queues drain without retry amplification and dependencies retain reserve while traffic is restored gradually. Lower error rate caused by dropping all traffic is not full recovery.

## Root-cause correction

Fix original defect/capacity problem and feedback mechanisms: retry budgets/backoff, bounded queues/concurrency, admission control, load isolation and tested degraded operation. Containment is not proof the initiating cause is fixed.

## Action safety

Load shedding, concurrency/retry changes, producer stop, scale, restart or rollback are `MUTATING_HIGH_RISK`. Require exact owned service/control, immutable config/version, maximum duration/amount, critical-work protection, dependency reserve, compensation/drain plan and observable rollback trigger. Block absent tested policy, unknown data semantics, unsupported class/tool, unvalidated core runbooks or missing graph-wide verification. No general `execute_runbook_action` extension is inferred.

## Human-in-the-Loop

Show who loses/delays work, precise control value/duration, expected measurable relief and full dependency blast radius. Coordinate owners through the incident process; each changed proposal needs approval. Argus does not send external notifications except through its existing authorized application flow.

## Forbidden actions

`FORBIDDEN`: restart all victims, purge queues, silently drop valuable work, blanket scale-to-zero, unlimited retries/timeouts, add capacity without dependency budget, bypass admission/auth or execute several speculative writes under one approval.

## Evidence preservation

Preserve compact topology/SLI/retry/queue/resource windows and action ordering; select snapshots within read budgets so diagnosis does not add meaningful overload. Protect payloads and customer identifiers.

## Verification

After each owner action, three source-fresh graph observations, then two complete 5-minute SLI windows and at least one relevant queue-drain/retry cycle. Good throughput rises, queue age/depth fall, retry multiplier and dependency pressure stabilize, and critical route objectives pass under restored traffic. Confirm accepted, rejected and dropped work by priority/cohort and remaining capacity; the service remains degraded until intentionally shed functionality is restored or explicitly accepted by the incident owner. New victim failures or reaccumulation stops restoration and escalates; do not claim whole-system recovery from one endpoint.

## Rollback

Owner restores previous admission/concurrency only in measured increments with dependency reserve. Dropped/expired work may be irreversible; replay requires idempotency/compensation review. No automatic queue, traffic or scaling rollback exists.

## Escalation

Incident commander plus dependency/platform/application owners for multi-service impact. Stop on missing load graph, protected workload risk, contradictory response or uncertain action. Attach supported propagation edges, queued/lost work, prior actions and one next discriminating observation.

## Recording / memory

Common record plus graph version, feedback hypothesis/counterevidence, action sequence, dropped/deferred work, coordinated owners and separate mitigation/recovery/root-cause outcomes.

## Prevention / follow-up

Validate simpler runbooks first, then retry/queue budgets, overload tests, priority shedding, isolated failure domains and capacity-loss exercises.

## Lab validation

Only after core validation: disposable frontend/backend and synthetic nonvaluable queue. Fix incoming rate at 10 requests/second; backend fixture accepts 5, client fixture retries at most twice with a 120-second watchdog and queue cap 100. Expect supported parent resource/dependency incidents, proposed RB-021 interpretation only when retry/queue telemetry exists, no victim mass restart. Denied/unsupported load-control proposal performs no write. Owner reduces only test producer rate below capacity, observes completion/queue drain through two windows and records all stages plus lost work. Replay simultaneous unrelated failures and missing retry metrics to require abstention. No cascade experiment has been executed.

## References

- [Google SRE cascading failures](https://sre.google/sre-book/addressing-cascading-failures/), [handling overload](https://sre.google/sre-book/handling-overload/), [incident response](https://sre.google/workbook/incident-response/).
- *Building Secure and Reliable Systems* (2020), “Design for Resilience,” PDF pp. 179, 193–194, for controlled degradation and recording remaining capacity.
- [Argus assessment](../RUNBOOK-ASSESSMENT.md) — current single-class execution constraints.

## Argus capability gaps

### Missing telemetry

Versioned dependency/load graph, retry amplification, queue age/drain, priority/cohort-specific shedding and tested remaining dependency capacity.

### Missing tools

`get_service_traffic_history`, `get_queue_health`, `get_retry_policy`, `get_dependency_capacity`; separately released load-control writes if justified.

### Tool improvements

Composite child freshness/failure provenance, temporal uncertainty and bounded graph-wide collection/verification.

### Detector improvements

Correlated overload detector without causal shortcuts; coordinated ownership, graph-wide safety predicates and validated-core activation gate.
