# RB-014 — Monitoring blind spot / exporter unavailable

## Metadata

```yaml
id: RB-014
title: Monitoring blind spot / exporter unavailable
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

Prometheus, Alertmanager, Argus/Node/cAdvisor/database exporters and registered probes for Host T. Record versions, scrape/rule intervals, discovery labels and source clock assumptions. Apply [shared contracts](../RUNBOOK-CONVENTIONS.md). Existing architecture stops at `undiagnosable` before the LLM when required detector metrics are stale/unavailable. This runbook describes operator diagnosis and a future dedicated observation path, not permission to bypass that rule.

## Incident definition

Required telemetry cannot establish the current state of a monitored service. Monitoring failure and monitored-service failure may coexist. Missing series are not zero values; query evaluation can select older samples within lookback. [Prometheus staleness](https://prometheus.io/docs/prometheus/latest/querying/basics/#staleness)

## User / service impact

Diagnostic confidence and detection coverage are reduced. Actual user impact remains unknown until independent service evidence is available; a telemetry outage does not prove the application is down or healthy.

## Trigger / detection conditions

Existing path: required metrics older than `METRICS_MAX_STALENESS` or adapter unavailable → `undiagnosable`, no model call, escalate. Proposed observability alert: target `up=0` for two scrape intervals; expected target/required-series absence for two intervals; stale source timestamp despite scrape success; rule/API failure. Pin expected inventory so an intentionally removed target is not blindly declared down. No dedicated RB-014 detector exists yet.

## Symptoms

Gaps, stale constant data, failed scrape, exporter endpoint error, absent target, Prometheus query errors, failed rules or missing notifications.

## Plausible causes / hypotheses

H1 monitored service failed; H2 exporter failed; H3 discovery/scrape config lost target; H4 network/DNS/auth/TLS fault; H5 Prometheus/rule failure; H6 stale cached/partial metric production; H7 Alertmanager routing/silence/inhibition; H8 intentional decommission/label change.

## Required evidence

Expected target/metric inventory, target health/last scrape/error, per-series source age and coverage, exporter process/HTTP state, independent service probe, rule/API state and relevant config/change metadata. Capture both scrape success and collector completeness.

## Required Argus tools

Existing reads may support an independently authorized operator investigation only when their execution prerequisites are met:

| Tool / input | Purpose / output | Safety class |
|---|---|---|
| `get_container_status(container)` | Exporter/runtime state if separately allowlisted | `READ_ONLY_SENSITIVE` |
| `check_http_endpoint(url, timeout_s=3)` | Exact approved exporter/service probe | `READ_ONLY_SENSITIVE` |
| `check_dns(name)` / `check_tcp_connection(host, port, attempts=2)` | Target-side reachability | `READ_ONLY_SENSITIVE` |
| `get_detailed_logs(container, since_minutes=15, max_lines=100)` | Bounded exporter error context | `READ_ONLY_SENSITIVE` |

Current lab target scope does not automatically include the entire monitoring plane. Missing scope is a permission gap, not a reason to widen targets during an incident. `MetricsPort.snapshot` is deterministic application infrastructure, not an invented model tool.

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_prometheus_target_status(target_id)` uses fixed HTTP API operations to expose discovery/scrape error/time; `get_metric_freshness(target_id, metric_profile)` returns expected-versus-present series and true source times; `get_monitoring_rule_status(rule_group_id)` returns evaluation error/time; `get_alert_delivery_status(alert_id)` returns authorized routing/inhibition/silence state. All `READ_ONLY_SENSITIVE` with bounded registered IDs, not arbitrary queries or config exports. The Prometheus API supplies target/rule/query status but needs a scoped Argus adapter. [Prometheus HTTP API](https://prometheus.io/docs/prometheus/latest/querying/api/)

## Diagnostic workflow

| Step | Action / reason | Interpretation / next step |
|---|---|---|
| 1 | Existing detect path checks required freshness | Stale/unavailable → undiagnosable, stop model investigation and escalate with last known times. Steps below are operator/future-path work. |
| 2 | Compare independent service probe to exporter/target status | Service healthy/exporter bad → H2–H6. Both bad → H1 plus visibility loss; do not choose one prematurely. |
| 3 | Expected inventory versus discovered targets | Missing target/labels → H3/H8. Present target scrape failing → 4. |
| 4 | DNS/TCP/TLS/auth and bounded exporter errors | Identify transport/auth/collector failure; credentials remain in adapters. Successful exporter HTTP is not proof required collectors work. |
| 5 | Prometheus API/rule status and per-series timestamps | Successful scrape but absent/stale required metric → H6/label change; API/rule error → H5. |
| 6 | If metrics/rules are healthy, inspect alert delivery state | H7 may explain missing notification but not missing samples. Keep paths distinct. |
| 7 | Owner repairs exact component; verify coverage then re-run normal detection | New valid evidence may reveal a real service incident previously hidden. |

## Decision tree

```text
required source samples fresh and complete? no -> undiagnosable; no model action
  operator -> expected target present? no -> inventory/discovery/config
              scrape fails? -> exporter/network/auth/TLS
              scrape succeeds but series stale/missing? -> collector/labels/cache
              series valid but alert absent? -> rule/routing/silence investigation
restore coverage -> fresh normal detection -> healthy or actual service incident
```

## Evidence interpretation

Prometheus alert rules have their own evaluation/pending semantics; Alertmanager groups/routes and may silence/inhibit notifications. Notification absence is not health evidence. [Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/), [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/)

## False positives and edge cases

Intended decommission, renamed labels, stale recording rules, scrape success with failed internal collector, cached DB readings, clock skew, partial target failure, monitor credentials succeeding where ordinary clients fail, and self-monitoring failure.

## Diagnosis outcome

Allow all common diagnostic labels in the operator record; current runtime outcome remains `undiagnosable` when mandatory telemetry is missing. Probable monitoring cause requires component evidence and independent service status; never claim healthy from empty results.

## Mitigation

Use an approved independent observer and escalate uncertainty. Monitoring owner repairs exporter/config/credentials or restores telemetry capacity through its change procedure. No automated restart of application victims.

## Recovery

Required targets/series and rules return with correct labels and fresh source times; normal detection resumes. If a real incident remains, investigate it instead of closing everything as recovered.

## Root-cause correction

Fix collection/config/permissions, inventory checks, capacity or alert routing; remove stale-data fallback behavior and establish independent monitoring of the monitoring path.

## Action safety

Exporter/Prometheus restart, credential/config and routing changes are `MUTATING_HIGH_RISK`. Require exact component/identity and config revision, preserved evidence, protected control-plane availability and reviewed rollback. Block missing monitoring scope, closed write gate, blind application restart or changing freshness rules to hide data loss. These are operator procedures, not supported default remediation.

## Human-in-the-Loop

Show visibility lost, actual application state if known, exact monitoring change, expected observation gap and rollback. Never treat elapsed time or regained notification delivery as approval to restart services.

## Forbidden actions

`FORBIDDEN`: substitute zero/healthy for missing data, bypass stale-detection guard, disable auth/TLS, dump scrape secrets, widen arbitrary queries/targets or silence the alert as recovery.

## Evidence preservation

Retain last-good source times, target inventory, sanitized scrape/rule errors and redacted config fingerprints in a healthy durable sink. Do not rely solely on the broken monitoring system to store its own evidence.

## Verification

After repair, three distinct complete source-fresh scrape observations and at least two successful rule evaluations, then 5 minutes without gaps. Check independent service health and re-run normal detectors. A healthy `/metrics` response or one `up=1` is insufficient. Missing labels, cached source values, rule errors or renewed gaps keep the incident open/escalated.

## Rollback

Monitoring owner retains last-good config/credential reference and restores it if the change reduces coverage; never restore an expired/revoked secret merely to remove errors. No automatic monitoring rollback exists.

## Escalation

Observability/platform owner immediately on loss of mandatory evidence, incident commander if service impact is unknown and critical. Attach last-good times, expected/actual series, component errors, independent probes and next required scoped check.

## Recording / memory

Common record plus coverage loss, confidence reduction, freshness provenance, no-model/no-write enforcement, owner repair and any newly uncovered incident.

## Prevention / follow-up

Inventory-aware absence alerts, collector health, source-age checks, independent observers and controlled rule/config tests. Keep unsupported incident classes visibly unsupported.

## Lab validation

With a healthy disposable API, operator stops only its exporter for 90 seconds at a 15-second scrape interval. Expect stale/unavailable detection → undiagnosable, zero model calls and zero application writes; independently verify API remains healthy. Restore exporter and separately replay cached old source values despite successful scrapes: no false recovery. An unauthorized monitoring target and denied restart must be refused. After owner repair require full fresh coverage/rules and normal detection for 5 minutes; record all stages including deliberately skipped model/action stages. No test has been run.

## References

- [Prometheus query staleness](https://prometheus.io/docs/prometheus/latest/querying/basics/#staleness), [HTTP API](https://prometheus.io/docs/prometheus/latest/querying/api/).
- [Alert rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/), [recording rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/), [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/).
- [Argus assessment](../RUNBOOK-ASSESSMENT.md) — fail-closed detector architecture.

## Argus capability gaps

### Missing telemetry

Expected-series inventory, true source-age/collector completeness, target/rule/delivery state and independent observer.

### Missing tools

`get_prometheus_target_status`, `get_metric_freshness`, `get_monitoring_rule_status`, `get_alert_delivery_status`.

### Tool improvements

Per-child timestamps/errors; no absent-as-zero; differentiate source collection from response time; monitoring target permission profile.

### Detector improvements

Dedicated monitoring diagnosis path designed without bypassing stale-workload guards; inventory-aware absence and cached-data checks.
