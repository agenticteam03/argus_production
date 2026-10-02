# RB-008 — Container crash loop, non-OOM

## Metadata

```yaml
id: RB-008
title: Container crash loop, non-OOM
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

Long-running Docker/Compose services expected to remain alive. Record Engine version, image digest, container ID, restart policy and expected process lifecycle. Exclude successful scheduled/one-shot jobs and supported OOM cases (RB-001). [Common contracts](../RUNBOOK-CONVENTIONS.md) apply; a dedicated non-OOM loop detector is missing.

## Incident definition

Repeated unexpected process exits prevent useful service operation, with OOM not established as the cause. Absence of retained OOM evidence does not prove a non-OOM cause; preserve uncertainty for unexplained kills.

## User / service impact

Measure request/job failures and available replicas. A container restarting behind healthy capacity may be partial degradation; successful job completion may be normal.

## Trigger / detection conditions

Proposed rule: at least three unexpected death/start cycles for one immutable service instance in 10 minutes, with service impact or failure to become ready. Existing RB-002 may detect stopped/unhealthy state but does not implement this loop rule. Cumulative counts and reused names are insufficient. Stale events/snapshots require abstention.

## Symptoms

Short uptime, repeated exits, exceptions, missing executable/configuration, permission/storage errors and failed startup readiness. Docker CLI launch errors and application exit codes are different evidence classes. [Docker exit status](https://docs.docker.com/engine/containers/run/#exit-status)

## Plausible causes / hypotheses

H1 application exception; H2 missing/invalid configuration; H3 dependency unavailable; H4 bad image/deployment/entrypoint; H5 permission or filesystem failure; H6 startup deadline; H7 external stop/kill or host/runtime event; H8 legitimate job completion misclassified as failure.

## Required evidence

Container/image identity, actual lifecycle events, exit/engine error, bounded prior-exit logs, restart policy, declared health/startup contract, dependency state, deployment/config fingerprints and host uptime. Never inspect raw environment values to prove configuration presence.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `get_container_status(container)` | Running/exit/OOM/state and identity | `READ_ONLY_SENSITIVE` |
| `get_restart_history(container, since_minutes=30)` / `get_container_events(container, since_minutes=30)` | Reconstruct actual exits/starts and gaps | `READ_ONLY_SAFE` |
| `get_detailed_logs(container, since_minutes=30, max_lines=150)` | Last visible failure, sanitized | `READ_ONLY_SENSITIVE` |
| `check_container_health(container)` / `check_connectivity(container)` | Startup and dependency alternatives | `READ_ONLY_SENSITIVE` |
| `get_disk_usage(path=None)` / `get_system_uptime()` | Filesystem capacity and host reboot context | `READ_ONLY_SAFE` |
| `inspect_service_config(container, config='main')` | Only declared redacted config | `READ_ONLY_SENSITIVE` |
| `capture_diagnostic_snapshot(container)` | Preserve state before intervention | `READ_ONLY_SENSITIVE` |

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_deployment_history(service_id, minutes)` with image/config fingerprints and source times, `READ_ONLY_SENSITIVE`; `get_startup_contract(container)` with redacted entrypoint, expected job/service behavior and readiness budget, `READ_ONLY_SENSITIVE`. Historical logs for a replaced/deleted ID need retained log storage; current-name logs are not a substitute.

## Diagnostic workflow

| Step | Action / why | Interpretation and next step |
|---|---|---|
| 1 | Bind ID and expected lifecycle; inspect state/events | Successful one-shot completion → wrong runbook. Correlated OOM → RB-001. Unknown kill → retain OOM/external alternatives. |
| 2 | Reconstruct three cycles and first failing log window | Repeat same exception supports H1; launch/config error supports H2/H4. Missing previous logs → gap, not absence of errors. |
| 3 | Check dependencies before local remediation | Failing dependency → RB-003; protect victim. Healthy dependency → 4. |
| 4 | Compare startup contract, health grace and resource/filesystem evidence | Permission/storage failure → owner/RB-005; deadline too short → H6; generic timeout remains ambiguous. |
| 5 | Compare image/config changes and host/runtime chronology | Regression hypothesis → RB-018; many simultaneous exits/reboot → RB-017/host owner. Correlation alone does not prove a bad image. |
| 6 | Preserve snapshot and select owner correction | Deterministic crash on every startup will recur after another restart; no blind retry. Verify after actual correction. |

## Decision tree

```text
unexpected repeated exit? no -> job/maintenance/stale trigger
  yes -> OOM supported? -> RB-001
         dependency fails? -> RB-003
         repeated exception/config/entrypoint error? -> application/deployment owner
         storage/permissions/deadline? -> focused correction
         host/runtime event? -> platform investigation
         unexplained -> multiple_hypotheses / insufficient_evidence
```

## Evidence interpretation

Docker restart policy governs when exits lead to restart; a health-state change alone is not evidence that Docker's restart policy restarted the process. Interpret counts with events and expected lifecycle. [Docker restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/)

## False positives and edge cases

Rolling replacement, manual stop, host reboot, missing retained events, log truncation, exit 0 on a service that should persist, successful batch job, signal kills without OOM evidence and startup grace mismatch.

## Diagnosis outcome

All common outcomes allowed. Probable cause requires the repeated failure mechanism and evidence excluding dependency/OOM alternatives. Unknown exit cause remains unresolved even when service later recovers.

## Mitigation

Operator can pause a proven harmful non-critical loop or restore a reviewed deployment. One approved restart is useful only after a transient cause has cleared and the current supported policy permits it; this runbook does not create that authority.

## Recovery

Corrected workload starts, stays useful across the former recurrence interval and serves representative requests/jobs. Restarting with unchanged deterministic failure is not recovery.

## Root-cause correction

Fix exception/configuration/entrypoint, permissions, startup budget or dependency lifecycle; test the exact artifact before release. Avoid masking a defect by increasing retry frequency.

## Action safety

Restart/stop/rollback/configuration writes are `MUTATING_HIGH_RISK`. Require exact target/ID and artifact, cause-cleared evidence, snapshot, workload-loss assessment, protected data and supported capability/class/gate. Block unresolved dependency, deterministic repeated crash, missing rollback compatibility or unknown last action. Production has no general deployment/stop capability; those remain owner procedures.

## Human-in-the-Loop

Show previous exits, corrected versus unchanged inputs, precise operation and expected lost work. Approval expires on identity/config change; denial/expiry means no write, and retry requires a new proposal.

## Forbidden actions

`FORBIDDEN`: unlimited restart loops, replace images with unpinned guesses, dump env/secrets, chmod/chown arbitrary paths, bypass failing startup checks or delete volumes to make startup succeed.

## Evidence preservation

Snapshot and retain first-failure logs/events plus image/config fingerprints before recreation or rollback; capture gaps for deleted instances. No raw secret-bearing config dumps.

## Verification

After completed correction, three fresh source observations, then `max(5 minutes, twice the previously observed cycle interval, configured startup budget)`. Intended artifact/identity, stable running/health, no repeated exception, successful representative work and healthy dependencies. Loss of telemetry or recurrence fails verification; timeout escalates with provisional state.

## Rollback

No undo for restart or lost in-memory work. Deployment owner uses previous immutable artifact only after schema/data compatibility review; rollback is separately approved and follows RB-018.

## Escalation

Application/release owner for repeated exceptions; platform for host/runtime failures. Stop after failed correction or unknown execution. Attach first-failure evidence, identities, corrected inputs, excluded hypotheses and next missing startup/deployment observation.

## Recording / memory

Common record plus expected lifecycle, exact exit sequence, image/config fingerprints, lost previous-ID evidence and recurrence interval.

## Prevention / follow-up

Startup contract tests, image/config validation, retention across recreation, bounded restart behavior and explicit job-versus-service metadata.

## Lab validation

Disposable fixture exits with code 1 every 15 seconds using a capped lab restart policy; label it as a persistent service. Capture at least three cycles within a 2-minute watchdog. Expect proposed/unsupported loop trigger, RB-008, repeated exception evidence, no OOM inference and refusal of another unchanged restart. Repeat as an intentional successful job and as a dependency failure; expect wrong-runbook/RB-003. Operator deploys the fixed fixture; exercise denial and then a new permitted proposal only where policy supports it. Verify stable work through the observation window and record detection, evidence, diagnosis, safety, action/no-action and outcome. Not executed.

## References

- [Docker run/exit status](https://docs.docker.com/engine/containers/run/#exit-status), [restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/).
- [Container inspection](https://docs.docker.com/reference/cli/docker/container/inspect/) and [Argus assessment](../RUNBOOK-ASSESSMENT.md).

## Argus capability gaps

### Missing telemetry

Retained per-instance logs, immutable deployment history and startup/job semantics.

### Missing tools

`get_deployment_history`, `get_startup_contract`.

### Tool improvements

Expose image/config fingerprints without secrets; distinguish death counts from actual restart cycles.

### Detector improvements

Identity-bound time-window detector with expected lifecycle and OOM uncertainty; no silent relabeling to bypass policy.
