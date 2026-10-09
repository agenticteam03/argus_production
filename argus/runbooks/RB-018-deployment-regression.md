# RB-018 — Deployment regression

## Metadata

```yaml
id: RB-018
title: Deployment regression
status: draft
owner: Argus Team
version: 1.1.1
created: 2026-09-29
last_reviewed: 2026-10-09
source_review_date: 2026-09-29
last_tested: null
detector: deployment_regression
```

## Scope

Versioned Docker/Compose application images, configuration and dependency/schema changes on declared services. Record immutable artifact/config digests, release transaction and compatibility assumptions. Exclude unsupported production rollout control. [Common contracts](../RUNBOOK-CONVENTIONS.md) apply; deployment detection and rollback execution are missing.

## Incident definition

Service behavior regresses in association with a release/config change, with evidence needed to support a causal mechanism. Temporal proximity alone does not prove causation. Comparing release cohorts under comparable conditions can strengthen attribution. [Google SRE canarying releases](https://sre.google/workbook/canarying-releases/)

## User / service impact

Identify affected release cohort/routes, error/latency/completion changes, data integrity concerns and remaining healthy capacity. A successful deployment command is not service success.

## Trigger / detection conditions

Proposed selection: fresh service objective breach after a known deployment, with an explicit comparison window (lab 30 minutes before/after) and sufficient matched traffic. Existing health/OOM/dependency detectors may initiate investigation; release correlation is a diagnostic branch, not a new current class. Missing release time/artifact means only a suspected change relationship.

## Symptoms

New exceptions, crash loops, error/latency increase, resource growth, bad config, dependency protocol mismatch or behavior isolated to a new release.

## Plausible causes / hypotheses

H1 code defect; H2 invalid config/secret reference; H3 incompatible schema/protocol; H4 missing resource/permission/dependency; H5 expected warmup/startup transient; H6 independent load/infrastructure incident; H7 mixed rollout or contaminated comparison baseline; H8 untrusted artifact/configuration or suspected compromise requiring security-owner investigation.

## Required evidence

Release event/actor, old/new immutable digests, configuration fingerprints without values, schema migration status/compatibility, cohort traffic/SLIs, first failure, resource/dependency timeline and known-good baseline provenance. The release owner must also establish artifact provenance and whether a proposed older version is still permitted under current security policy. A mutable image tag is not a stable artifact identity. [Docker image references](https://docs.docker.com/engine/containers/run/#image-references)

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `get_container_status(container)` / `get_container_events(container, since_minutes=60)` | Current identity and lifecycle evidence | `READ_ONLY_SENSITIVE` |
| `get_detailed_logs(container, since_minutes=30, max_lines=150)` | First post-change errors, redacted | `READ_ONLY_SENSITIVE` |
| `inspect_service_config(container, config='main')` | Declared redacted configuration only | `READ_ONLY_SENSITIVE` |
| `compare_incident_baseline(container)` | Current versus helper baseline; must verify baseline was healthy | `READ_ONLY_SAFE` |
| `correlate_incident_timeline(container, minutes=60)` | Service/dependency chronology, not complete release history | `READ_ONLY_SENSITIVE` |
| `get_cpu_history(container, minutes=60)` / `get_memory_history(container, minutes=60)` | Resource comparison | `READ_ONLY_SAFE` |
| `capture_diagnostic_snapshot(container)` | Preserve faulty-instance evidence before replacement | `READ_ONLY_SENSITIVE` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_deployment_history(service_id, minutes)` returns release/digest/config/schema metadata; `compare_release_cohorts(service_id, release_ids, minutes)` returns traffic-normalized SLIs and coverage; `get_release_compatibility(service_id, from_digest, to_digest)` exposes approved migration/rollback compatibility. These are `READ_ONLY_SENSITIVE`. Approved artifact provenance and current security status are also required before any release restore; no such Argus contract was found. **MISSING TOOL REQUIREMENT:** `rollback_deployment(service_id, release_digest, expected_current_digest)` would be a separately gated `MUTATING_HIGH_RISK` capability; no arbitrary image URL/tag or migration shell.

## Diagnostic workflow

| Step | Action / why | Interpretation / next step |
|---|---|---|
| 1 | Establish actual release and first failure time/identity | Missing release evidence → hypothesis only. Failure predates release → H6 or pre-existing issue. |
| 2 | Compare matched cohorts/healthy baseline with adequate representative exposure | New cohort alone worsens → H1–H4 supported; all cohorts worsen → demand/dependency or shared-backend contamination. A tiny or off-peak canary may miss route/load defects. Check absolute service objectives as well as relative cohort difference; missing metrics are not non-abnormal. |
| 3 | Logs/config fingerprints and lifecycle | Reproducible new error supports mechanism; don't expose env to inspect secret references. |
| 4 | Dependencies/resources/warmup timeline | Capacity/dependency event → owning runbook; startup transient → bounded wait only within approved budget. |
| 5 | Check migration, artifact provenance and current security policy before proposing change | Unknown/destructive schema effects, incompatible prior image, vulnerable prior release or untrusted artifact → block ordinary rollback and escalate to release/security owner. Forward repair may be necessary. |
| 6 | Snapshot and owner chooses exact compatible artifact | Current Argus escalates deployment changes; verify all affected cohorts after owner action. |

## Decision tree

```text
release precedes credible regression?
  no/unknown -> independent incident or insufficient_evidence
  yes -> new cohort differs under matched demand?
           no -> shared dependency/load/baseline investigation
           yes -> mechanism in code/config/schema/resources?
                    supported -> compatibility review
                    unknown -> probable association only
compatible, trusted, security-permitted rollback artifact? no -> forward repair / escalation
```

## Evidence interpretation

Time order and one error spike are not proof. Current baseline helper chooses historical data without proving it was healthy and can omit/misclassify missing current metrics; independently validate coverage. Restarting a container does not select a prior image/config release.

## False positives and edge cases

Traffic mix changes, cold caches, migrations affecting both cohorts, mutable tags, host pressure during builds, partial rollout, feature flags, release clock skew, old baseline already degraded and containers recreated under the same name. A before/after comparison without concurrent control is vulnerable to time-of-day demand changes; a shared backend can make both canary and control degrade together.

## Diagnosis outcome

All common outcomes allowed. Probable regression names artifact/config and supported mechanism with matched comparisons; a correlated deployment with missing compatibility or baseline remains uncertain and unsafe to roll back automatically.

## Mitigation

Release owner pauses further rollout or restores a tested compatible artifact through the existing deployment system. Feature-flag/traffic changes require their own owned contracts. Current Argus offers no deployment write.

## Recovery

Intended compatible artifact runs across the affected cohort and service objectives recover with representative load, healthy dependencies and no new data integrity signals.

## Root-cause correction

Fix code/config/schema protocol, strengthen canary and compatibility tests, then deploy a corrected version. Rollback restores service but may leave the defect unresolved for the next release.

## Action safety

Pause/rollback/config/schema writes are `MUTATING_HIGH_RISK`. Bind service, current/desired immutable digests, exact rollout scope, config/schema compatibility, trusted artifact provenance, current security status, protected data and rollback/forward-repair plan; preserve faulty instance evidence. Block unknown migrations, unavailable or vulnerable prior artifact, suspected tampering, unreviewed secret changes, active rollout race or missing tool/profile. Route suspected compromise through the security-owned incident process; routine service restoration must not destroy needed evidence or reintroduce an attack path. Database reversal is never implicit in application rollback.

## Human-in-the-Loop

Show old/new artifacts, affected cohort, evidence and alternatives, compatibility attestations, exact rollout operation and data risks. Any changed current digest cancels approval. An incident-level “roll back” intention is not an executable proposal.

## Forbidden actions

`FORBIDDEN`: pull arbitrary/latest images, destructive schema reversal without an approved migration plan, wipe volumes, replay data blindly, auto-rollback from correlation alone or dump secrets to compare configuration.

## Evidence preservation

Snapshot faulty instance, retain image/config fingerprints and redacted logs, release/migration audit and matched SLI windows before replacement. Logs tied only to current names are insufficient after recreation.

## Verification

Three fresh post-change identity/health observations, then two complete 5-minute SLI windows with matched representative traffic. Confirm exact desired digest/config/schema, recovered errors/latency/completion, and no hidden bad cohort. Old rolling samples, low traffic, rollout drift or new incompatibility prevents closure. Timeout/recurrence escalates.

## Rollback

This procedure's rollback is itself the proposed mitigation and has compatibility, provenance and current security gates. If it worsens the incident, the owner chooses a validated forward fix or compatible saved release; do not oscillate automatically between versions. A release once labeled healthy is not automatically safe to restore after a vulnerability or suspected compromise. No automatic rollout undo is currently implemented.

## Escalation

Release/application owner, DBA for schema compatibility, incident commander for broad impact. Attach artifact chronology, cohort comparisons, mechanism/counterevidence and exact unresolved compatibility question.

## Recording / memory

Common record plus release/current/desired digests, config/schema fingerprints, comparison provenance, compatibility decision, owner action and unresolved defect ticket.

## Prevention / follow-up

Immutable artifacts, staged rollout with representative canary size/duration and bounded user exposure, automated compatibility tests, deployment event telemetry and release cohorts in SLIs.

## Lab validation

Two disposable compatible API versions with equal synthetic traffic: new version deterministically returns 500 on one harmless route; retain old version and identical schema. Expect existing health/error context→RB-018, cohort-specific evidence and refusal of a fabricated rollback tool. Owner tests denial then exact approved deployment-system rollback; verify two full SLI windows and record all stages. Repeat with an incompatible schema fixture and a metadata fixture marking the prior version security-disallowed: rollback must be blocked in both cases despite apparent new-version correlation. Also replay an independent dependency failure affecting both versions. No rollout was executed.

## References

- [Google SRE canarying releases](https://sre.google/workbook/canarying-releases/), [Docker image references](https://docs.docker.com/engine/containers/run/#image-references). *The Site Reliability Workbook* (2018), “Canarying Releases,” PDF pp. 374–381, discusses representative exposure, control contamination and absolute objectives.
- *Building Secure and Reliable Systems* (2020), “Design for Recovery” and “Recovery and Aftermath,” PDF pp. 219, 230–232, 462, for security-aware restore and rollback.
- [Argus assessment](../RUNBOOK-ASSESSMENT.md) — baseline helper and missing deployment capabilities.

## Argus capability gaps

### Missing telemetry

Immutable release/config/schema history, approved artifact provenance and current security status, proven healthy baseline and matched cohort SLIs.

### Missing tools

`get_deployment_history`, `compare_release_cohorts`, `get_release_compatibility`; separately released `rollback_deployment` if desired.

### Tool improvements

Missing data cannot mean non-abnormal baseline; include artifact identity and evidence coverage.

### Detector improvements

Release-linked impact detection without automatic causal attribution; separate compatibility, provenance, security-status and rollback policy gates and permissions.
