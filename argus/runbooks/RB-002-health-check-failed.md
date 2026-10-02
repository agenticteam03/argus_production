# RB-002 — Service/container health check failure

## Metadata

```yaml
id: RB-002
title: Service/container health check failure
status: draft
owner: Argus Team
version: 1.0.0
created: 2026-09-29
last_reviewed: 2026-09-29
source_review_date: 2026-09-29
last_tested: null
detector: health_check_failed
```

## Scope

Linux Docker/Compose service with declared endpoint and dependencies. Record Engine version, immutable container ID, health configuration and probe origin. Docker `start-interval` requires Engine 25 or later; do not assume it on older installations. Exclude intentional shutdown/maintenance after checking change records. Apply [shared contracts](../RUNBOOK-CONVENTIONS.md); broader actions remain extensions.

## Incident definition

The expected service is absent/stopped, Docker reports unhealthy, or a declared endpoint fails its configured acceptance contract. These are distinct observations. Docker health has its own `starting`, `healthy`, and `unhealthy` states and configured failure count; process state is separate. [Docker HEALTHCHECK](https://docs.docker.com/reference/dockerfile/#healthcheck)

## User / service impact

Measure failed requests and affected routes. A broken health command can coexist with working user requests; an internal healthy endpoint can coexist with a failed public route. If only health telemetry is available, actual user impact remains unknown.

## Trigger / detection conditions

Existing `health_check_failed` checks `present=false`, `running=false`, `unhealthy=true`, or `endpoint_count>0 && endpoint_ok=false` on fresh snapshots. No duration is enforced in that detector. Proposed alert policy: sustain unexpected endpoint failure for `max(60 seconds, 2*S)` outside maintenance/startup grace, while severe user impact starts immediate investigation. Missing endpoint configuration or samples does not mean endpoint health.

## Symptoms

Stopped/missing process, unhealthy status/failing streak, probe timeout, unexpected HTTP status, dependency errors or repeated transitions.

## Plausible causes / hypotheses

H1 process crash/startup failure; H2 health command/configuration mismatch; H3 process deadlock/event-loop blockage; H4 failed dependency makes this service a victim; H5 network/proxy/TLS path failure; H6 stale alert or already recovered service. Resource starvation can cause H3-like symptoms without a software deadlock.

## Required evidence

Fresh identity/state, health command and timing settings, bounded health output, endpoint status/latency from the affected path, dependency observations, startup/change times, resource history and application errors. Missing a public vantage limits impact conclusions.

## Required Argus tools

Existing code, subject to deployment availability:

| Tool / input | Purpose and output | Safety class |
|---|---|---|
| `get_container_status(container)` | ID, running/exit/OOM and health | `READ_ONLY_SENSITIVE` |
| `check_container_health(container)` | Command, interval/timeout/retries/start period if supplied, last outputs | `READ_ONLY_SENSITIVE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Timed/redacted errors | `READ_ONLY_SENSITIVE` |
| `check_http_endpoint(url, timeout_s=3)` | Allowlisted app-network HTTP result | `READ_ONLY_SENSITIVE` |
| `check_connectivity(container)` | Declared dependency DNS/TCP observations | `READ_ONLY_SENSITIVE` |
| `trace_request_path(container)` | Composite observations by declared hop; inspect child failures | `READ_ONLY_SENSITIVE` |
| `get_container_resources(container)` / `get_cpu_history(container, minutes=30)` | Instant resources and CPU history to test starvation | `READ_ONLY_SAFE` |
| `capture_diagnostic_snapshot(container)` | Evidence before restart | `READ_ONLY_SENSITIVE` |
| `restart_container(container)` | Exact approved container restart via local dispatcher | `MUTATING_HIGH_RISK` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_external_probe_history(endpoint_id, minutes)` from a registered Blackbox/external vantage: probe origin, timestamps, status and latency, `READ_ONLY_SAFE`. Existing HTTP reads originate in the app network, not the public client path. Blackbox supports multiple probe protocols but must be explicitly deployed/configured. [Blackbox Exporter](https://github.com/prometheus/blackbox_exporter)

**MISSING TOOL REQUIREMENT:** versioned deployment history and a bounded application-progress diagnostic for deadlock attribution. Full health timing/config fields are an extension if the inspected gateway omits them. No arbitrary health-command execution or container shell fallback.

## Diagnostic workflow

| Step | Action / why | Interpret and proceed |
|---|---|---|
| 1 | Status and trigger timestamps: verify current failure/identity | Missing/stopped: inspect exit; OOM → RB-001, other crash → RB-008. Running → 2. |
| 2 | Health config/output: distinguish test failure from process failure | No health check → rely on declared endpoint, never assume healthy. `starting` within approved grace → bounded observation. Failing executable/path or wrong port → H2; continue 3. |
| 3 | Probe same configured application route and affected external path | Internal succeeds/external fails → H5, RB-009/RB-015/RB-016. Both succeed → confirm fresh sustained recovery. Both fail → 4. |
| 4 | Dependency matrix, then protocol/capacity evidence through RB-003 | Dependency failure → diagnose dependency; block victim restart. TCP success alone cannot clear dependencies. All dependencies healthy → 5. |
| 5 | Logs/resources/history and bounded application progress | Starvation → relevant resource runbook. Progress stops despite capacity/dependency health → H3 supported, not proved. Missing progress evidence → multiple hypotheses. |
| 6 | Snapshot, policy proposal only if justified, then verify | Configuration failure needs owner correction; restart only for an evidenced process failure with enforceable predicates. |

## Decision tree

```text
running? no -> OOM or non-OOM startup/crash investigation
  yes -> Docker unhealthy? yes -> inspect test and startup grace
         endpoint failing? no -> test misconfiguration or recovery
           yes -> dependency failing? yes -> RB-003; protect victim
                  external path only? yes -> network/proxy/TLS
                  resource saturation? yes -> resource runbook
                  process stalled + safe predicates? -> approved restart candidate
                  otherwise -> insufficient_evidence / escalate
```

## Evidence interpretation

An unhealthy transition means the configured test failed, not that restart will fix it. Compare the exact tested path, expected status and dependencies. Require application evidence before calling a timeout a deadlock. Temporal overlap with deployment supports investigation, not automatic rollback.

## False positives and edge cases

Long startup, health test executable absent, authentication redirect, wrong expected status, cached success, a health endpoint with no dependency checks, no Docker health configured, probe credentials failing, maintenance or container replacement. Sanitize health commands/output because they can contain secrets.

## Diagnosis outcome

Permit `probable_root_cause`, `multiple_hypotheses`, `insufficient_evidence`, `incident_no_longer_present`, `wrong_runbook`. Include evidence for the failing layer, evidence against a failed dependency, and unobserved client paths. A missing external probe limits closure claims.

## Mitigation

Operator may divert traffic using an established service procedure. Argus may propose one allowed restart for an evidenced wedged process; do not repeatedly restart a booting or dependency-blocked service.

## Recovery

Restore Docker health where configured and the affected application route from its actual vantage. Dependency health and representative request success must agree.

## Root-cause correction

Fix the health contract/startup grace, underlying application stall, resource constraint, or dependency/path defect. A restart is temporary recovery. Configuration deployment is a separately approved operator change.

## Action safety

`restart_container(container)` is `MUTATING_HIGH_RISK`: bind exact allowlisted name/ID, preserve snapshot, check dependency health, capacity, criticality, maintenance and incident freshness; blast radius includes in-flight requests and reconnects. Block unknown dependency state, active startup grace, missing predicate enforcement, closed gate, replaced ID, unapproved critical target or prior uncertain action. No mutating low-risk path is assumed. Traffic/config changes have no available write contract here and remain operator work with exact target/config version, rollback and approval.

## Human-in-the-Loop

Show failure layer, command versus endpoint evidence, outage risk, target/ID, exact restart arguments and verification window. Approval is single-use and digest-bound; denial/expiry produces no write. Apply shared precheck and audit rules.

## Forbidden actions

`FORBIDDEN`: disable health checks to clear alerts, restart victims of failed dependencies, arbitrary exec of health command text, dump env/config secrets, or unbounded restart attempts.

## Evidence preservation

Snapshot before restart; separately preserve health timing/output, external/internal probe results and relevant dependency refs. Missing snapshot components are recorded; do not erase the only failure evidence without operator escalation.

## Verification

After action completion, use three distinct source-fresh samples spanning at least `2*S`, then observe for `max(5 minutes, configured startup grace + two health-check intervals)`. All expected health and route checks pass, restart count stays stable, dependencies accept work. Any recurrence, stale probe or unavailable critical path fails closure. If `VERIFY_TIMEOUT` is shorter, escalate with provisional recovery. No-action recovery is external resolution.

## Rollback

Restart has no automatic undo. A separately reviewed health/config deployment must retain the previous config/image and restore it through its owner after evaluating whether rollback reintroduces the original defect.

## Escalation

Application on-call for stalled/test-misconfigured process; platform/network owner for path failure; dependency owner via RB-003. Stop on absent evidence, write refusal, recurring failure or unknown restart result. Attach paired probe results, health settings, logs and timeline; request the missing progress/public-path observation next.

## Recording / memory

Common record plus internal/external vantage, health config version, failure layer, startup grace, dependency exclusions, approval and post-action samples. Keep restored service separate from fixed defect.

## Prevention / follow-up

Test health endpoints under slow startup and dependency loss; document liveness/readiness purpose; retain external probes and configuration fingerprints; implement dependency-aware restart predicates.

## Lab validation

Disposable API fixture: (A) health command checks an unused port while its real endpoint remains healthy; (B) configured dependency is stopped; (C) test endpoint is deliberately blocked in a controllable handler while dependencies stay healthy. Use a 15-second test interval and 3 failures; impose a 5-minute abort. Expect health detector → RB-002; H2 for A, RB-003/victim protection for B, possible process stall for C. A/B must not produce victim restart. For C exercise denial then one new approved proposal after snapshot; remove the injected stall through the lab fixture and verify fresh internal/external health. Retain detection, evidence, diagnosis, policy refusal/approval, action, verification and record artifacts. Also replay absent probe data: no healthy conclusion. No lab result is claimed.

## References

- [Docker HEALTHCHECK](https://docs.docker.com/reference/dockerfile/#healthcheck) — status/timing semantics.
- [Blackbox Exporter](https://github.com/prometheus/blackbox_exporter) — independent probe capabilities.
- [Argus code/policy assessment](../RUNBOOK-ASSESSMENT.md) — detector and execution constraints.

## Argus capability gaps

### Missing telemetry

Public-path history, complete health timing and application progress evidence.

### Missing tools

`get_external_probe_history`; bounded application-progress and deployment-history contracts.

### Tool improvements

Expose health config safely; preserve per-child freshness/errors in composites; report exact probe acceptance contract.

### Detector improvements

Duration/startup/maintenance handling and independent endpoint freshness; implement restart predicates rather than prose-only requirements.
