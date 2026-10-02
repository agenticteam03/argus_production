# RB-011 — HTTP high latency / elevated error rate

## Metadata

```yaml
id: RB-011
title: HTTP high latency / elevated error rate
status: draft
owner: Argus Team
version: 1.1.0
created: 2026-09-29
last_reviewed: 2026-09-29
source_review_date: 2026-09-29
last_tested: null
detector: null
```

## Scope

Declared HTTP routes through NGINX/API/dependencies on Host T. Record route, expected statuses, timeout, authentication profile, histogram format and software versions. Exclude arbitrary user URLs and writes used as probes. Follow [shared contracts](../RUNBOOK-CONVENTIONS.md); dedicated latency/error detection is missing.

## Incident definition

User request latency or unsuccessful-response rate exceeds the service's agreed objective under meaningful traffic. Investigate latency, traffic, errors and saturation together; internal and external observations answer different questions. [Google SRE monitoring](https://sre.google/sre-book/monitoring-distributed-systems/)

## User / service impact

Identify affected routes, tenants/cohorts and slow versus failed requests without collecting customer payloads. Measure successful throughput too; a quiet endpoint with no errors may simply have lost all traffic.

## Trigger / detection conditions

Proposed trigger: use the service's agreed, versioned user-facing SLI/SLO and alert policy. Where the SLI counts bad requests (including requests slower than its latency threshold), evaluate error-budget burn over a long window and a short window that confirms the budget is still being consumed; choose windows and paging thresholds from the service's response-time needs and test them against historical incidents. Also require a meaningful request denominator. An independently confirmed broad outage can merit immediate incident coordination even before a sustained alert matures. For low-traffic routes, evaluate a separately defined safe synthetic probe or an appropriately scoped aggregate without mixing synthetic requests into the real-user SLI. No universal burn, latency or traffic threshold is supplied. Undefined objective, missing denominator or absent metric means uncalibrated/insufficient evidence. Current binary endpoint failure may route via RB-002 but is not an implemented latency detector.

## Symptoms

Slow successful responses, timeouts, 5xx or route-specific unexpected status, falling good throughput, retries and queue growth.

## Plausible causes / hypotheses

H1 traffic/concurrency overload; H2 slow/unavailable dependency; H3 CPU/memory/I/O saturation; H4 proxy/TLS/network issue; H5 code/config regression; H6 expensive route/query or cache miss; H7 authentication/client/config issue; H8 telemetry artifact or low-volume noise.

## Required evidence

Same-window latency distribution, total/success/error counts, route/status classes, queue/saturation, dependency timings, safe request-path trace metadata and deployment history. Preserve SLI/SLO and alert-policy versions, bad-event definition, budget window, short/long burn windows and request denominators. Keep synthetic-probe outcomes separate from real-user observations; preserve source vantage and distinguish edge latency from application processing.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `check_http_endpoint(url, timeout_s=3)` | Bounded allowlisted GET; individual status/latency | `READ_ONLY_SENSITIVE` |
| `trace_request_path(container)` | Declared hop checks, not distributed tracing | `READ_ONLY_SENSITIVE` |
| `get_cpu_history(container, minutes=30)` / `get_memory_history(container, minutes=30)` | Resource correlation | `READ_ONLY_SAFE` |
| `get_io_metrics()` | Current storage pressure | `READ_ONLY_SAFE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Sanitized error/timeout context | `READ_ONLY_SENSITIVE` |
| `inspect_database_health(container)` | Relevant DB capacity/waits | `READ_ONLY_SENSITIVE` |
| `correlate_incident_timeline(container, minutes=30)` | Change/error chronology | `READ_ONLY_SENSITIVE` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_latency_history(service_id, route_id, minutes)` and `get_service_traffic_history(service_id, minutes)` expose distribution/count/error denominators with coverage, `READ_ONLY_SAFE`; `get_request_trace_summary(service_id, trace_id)` returns allowlisted span timings/errors with no payload/secret headers, `READ_ONLY_SENSITIVE`; deployment/external-probe history shared with other runbooks. Versioned SLI/SLO definitions, error-budget policy, alert windows and synthetic-probe identity must be available to the detector before any burn-rate selection is implemented. `trace_request_path` is not an OpenTelemetry trace implementation.

## Diagnostic workflow

| Step | Action / reason | Interpretation / next step |
|---|---|---|
| 1 | Confirm objective breach, volume and sample quality; check both burn windows when configured | Too few real requests/unknown SLO → use the approved low-traffic path or qualify uncertainty. Long-window breach without current short-window burn may be historical, not an active page. Credible active impact → 2. |
| 2 | Compare edge and app probes, status classes and successful throughput | Edge-only failure → RB-015/016/009. Matching app degradation → 3. |
| 3 | Trace declared dependencies and DB state | Failed/slow dependency → RB-003/013; protect victim. No discriminating timing → request trace summary. |
| 4 | Align CPU/memory/I/O and queue history with traffic | Saturation rises before latency → resource/load hypothesis; normal resource headroom weakens it but does not prove code fault. |
| 5 | Compare route/query/deployment cohorts | One route or new artifact degrades → H5/H6; all clients/auth profile changes → H7. Correlation alone is insufficient for rollback. |
| 6 | Preserve distribution and failure evidence, choose owner mitigation | Missing denominator or dependency timing keeps multiple hypotheses; avoid a blind restart. |

## Decision tree

```text
credible active SLI breach + sufficient real-user traffic?
  no -> approved low-traffic probe / telemetry / contract investigation
  yes -> edge-only? -> proxy/network/TLS
         dependency slow? -> dependency owner
         saturation + queue? -> capacity/resource branch
         route/artifact-specific? -> application/regression investigation
         none discriminates? -> insufficient_evidence
```

## Evidence interpretation

For counters use reset-aware rates before aggregation; classic histogram quantiles require bucket-compatible aggregation including `le`. Do not average precomputed percentiles or combine incompatible histograms. Native histogram handling depends on the deployed Prometheus version. Empty traffic denominators are unknown/not-applicable, not zero errors. [Prometheus functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)

## False positives and edge cases

Low request count, changed route labels/buckets, failed requests excluded from latency, counter reset, health endpoint cheaper than real work, cached responses, retry amplification, timeout censoring and a changed probe origin. A green synthetic probe may miss a failing user route; mixing its successes with real-user counts can hide impact. A long-window breach after recovery is not proof of current burn.

## Diagnosis outcome

All common outcomes allowed. Probable diagnosis needs route/vantage and time-aligned causal-mechanism evidence plus alternatives; do not equate a 5xx with a specific backend cause.

## Mitigation

Owner can reduce non-critical load, shed approved traffic or restore a compatible known-good release. These are separately controlled procedures; Argus has no generic traffic-management or rollback write capability. Restart requires an independently evidenced process-stall case under RB-002.

## Recovery

Objectives and successful throughput recover for the affected route/cohort, dependencies are healthy and backlog is draining under restored demand.

## Root-cause correction

Fix expensive code/query, retry behavior, dependency issue, capacity or regression. Temporary load reduction is not a performance fix; record dropped functionality.

## Action safety

Traffic shedding, rollback/config changes and restarts are `MUTATING_HIGH_RISK`. Require precise route/service/artifact and identity, protected clients/transactions, capacity and compatibility checks, bounded duration and rollback. Block unknown user impact, untested health probe semantics, absent tool/profile or missing deterministic predicates. GET probes must be configured as harmless endpoints; do not replay business transactions.

## Human-in-the-Loop

Show affected cohort, accepted/dropped traffic, exact operation and expected objective change. Frozen approval is required for each write; a general latency alert is not permission to change retries/timeouts.

## Forbidden actions

`FORBIDDEN`: disable alerts, hide errors by changing success definitions, unbounded retries/load tests, replay payments/writes as probes, expose traces with secrets, or restart every service on the path.

## Evidence preservation

Preserve compact same-window distributions/counts and redacted trace/error refs plus artifact identity before change. Retain no request bodies, tokens or raw customer identifiers.

## Verification

Three post-action source-fresh samples, followed by two complete 5-minute SLI windows with sufficient traffic. Success: configured latency/error objective met, good throughput restored, queue drains and dependency/resource metrics agree. Old rolling-window samples cannot prove immediate post-action recovery. Low traffic, gaps, recurrence or short verification timeout yields provisional state and escalation.

## Rollback

Owner restores previous traffic/config/artifact through a reviewed compatible change. Preserve old limits and queue implications; undoing mitigation must not instantly restore overload. No automatic rollback exists in current Argus.

## Escalation

Application/incident commander for broad user impact; platform or dependency owner by evidence. Attach SLI definitions/denominators, route/vantage, correlated resource windows and missing discriminating trace; stop speculative actions.

## Recording / memory

Common record plus SLO/SLI version, histogram/count semantics, affected cohort, successful throughput and service versus root-cause recovery.

## Prevention / follow-up

Golden-signal dashboards, appropriate SLO alerts, bounded retries, route budgets, safe trace redaction and representative load tests.

## Lab validation

Disposable API receives 10 harmless requests/second for a fixed 2-minute baseline; inject 500 ms delay on half the requests for 2 minutes, then separately return synthetic 500 responses on 20%. Set the lab objective, bad-event definition and short/long alert windows before testing; this short fixture does not validate a longer production window. Expect proposed/unsupported RB-011 trigger, latency versus error evidence, no invented dependency/CPU cause, and no blind restart. Reject a mutating probe URL. Operator clears the fixture; verify two full 5-minute windows under the same load and record all stages. Replay zero traffic, one failed request on a quiet route, an independently green probe that misses a broken user route, a recovered short window with an older long-window breach, and a counter reset. None may yield false healthy service or an invented active page. Not executed.

## References

- [Google SRE monitoring](https://sre.google/sre-book/monitoring-distributed-systems/), [Prometheus functions](https://prometheus.io/docs/prometheus/latest/querying/functions/).
- *The Site Reliability Workbook* (2018), “Alerting on SLOs,” PDF pp. 107–121, for active short/long budget burn and low-traffic caveats.
- [Argus assessment](../RUNBOOK-ASSESSMENT.md) — actual composite capabilities.

## Argus capability gaps

### Missing telemetry

Request distribution/counts, route objectives and alert-policy version, short/long budget burn, queue/progress, redacted span timings and separate external/synthetic vantage.

### Missing tools

`get_latency_history`, `get_service_traffic_history`, `get_request_trace_summary`, deployment/probe history.

### Tool improvements

Distinguish path probes from traces; explicit units, denominators, reset handling, source timestamps and probe success contract.

### Detector improvements

SLI/SLO-aware detector with configured short/long active-burn logic where the objective counts bad events, a separate low-traffic path, request denominators and missing-series state; binary health is insufficient.
