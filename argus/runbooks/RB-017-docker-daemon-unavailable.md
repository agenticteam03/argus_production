# RB-017 — Docker daemon unavailable/degraded

## Metadata

```yaml
id: RB-017
title: Docker daemon unavailable/degraded
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

Docker Engine/runtime and Argus gateways on Linux Host T. Record Engine/API/systemd/containerd versions, storage driver and live-restore configuration. Exclude assuming all workloads stopped because the control API is unavailable. [Common contracts](../RUNBOOK-CONVENTIONS.md) apply; no dedicated runtime detector or restart-service capability exists.

## Incident definition

Expected Docker control-plane observations/operations fail or degrade. The cause can be the daemon, its socket/auth path, an Argus gateway or host resources. Docker daemon troubleshooting distinguishes connectivity/configuration problems from daemon process state. [Docker daemon troubleshooting](https://docs.docker.com/engine/daemon/troubleshoot/)

## User / service impact

Container inspection/remediation/deployment may be unavailable while running applications still serve traffic. Independently measure workload endpoints and observability. Record control-plane and application impact separately.

## Trigger / detection conditions

Proposed trigger: repeated bounded runtime-read failures across two declared targets for at least `max(60 seconds, 2*S)`, plus gateway/daemon path evidence; a single refused target is not daemon failure. Current metric loss may route to RB-014/undiagnosable. Missing runtime tools cannot justify bypassing the gateway.

## Symptoms

API timeouts/connection errors, gateway 401/403/5xx, missing runtime inventory, daemon startup failures, storage errors and widespread inspect failures.

## Plausible causes / hypotheses

H1 read gateway down; H2 network/tunnel/auth or exact-route policy fault; H3 daemon stopped/crashed; H4 daemon misconfiguration/startup failure; H5 host memory/disk/I/O pressure; H6 runtime/storage-driver degradation; H7 API incompatibility; H8 isolated target not found/replaced.

## Required evidence

Error category/route, independent gateway and daemon health, host service state, approved runtime journal, host resources, workload probes, target identity and runtime/config change history. Avoid raw Docker info/inspect/env dumps containing secrets or unrestricted host data.

## Required Argus tools

| Existing tool / input | Purpose / output | Safety class |
|---|---|---|
| `get_container_list()` / `get_container_status(container)` | Bounded allowlisted runtime observations/errors | `READ_ONLY_SENSITIVE` |
| `get_journal_logs(unit='docker', since_minutes=30)` | Docker unit journal; only docker/containerd enum supported | `READ_ONLY_SENSITIVE` |
| `get_host_memory()` / `get_disk_usage(path=None)` / `get_io_metrics()` | Independent host pressure if probe survives | `READ_ONLY_SAFE` |
| `get_system_uptime()` | Boot context | `READ_ONLY_SAFE` |
| `check_http_endpoint(url, timeout_s=3)` | Registered workload health independent of daemon API | `READ_ONLY_SENSITIVE` |

Host/journal/probe dependencies may fail together; a tool error is not an empty healthy result. Journal collection uses a bounded approved unit, consistent with systemd's unit filtering. [systemd journalctl source manual](https://raw.githubusercontent.com/systemd/systemd/main/man/journalctl.xml)

## Missing tools

**MISSING TOOL REQUIREMENT:** `get_runtime_gateway_status(gateway_id)` returns route/auth/transport health; `get_docker_daemon_status(host_id)` returns allowlisted ping/version and daemon service state; `get_service_state(host_id, unit_id)` returns approved systemd state/start/error with no general unit enumeration. All `READ_ONLY_SENSITIVE`. **MISSING TOOL REQUIREMENT:** a separately released `restart_service` capability if desired; it is roadmap-only, not current authority.

## Diagnostic workflow

| Step | Action / why | Interpretation / next step |
|---|---|---|
| 1 | Classify read refusal/not-found/transport error | One disallowed/replaced target → H2/H8, not daemon outage. Several runtime failures → 2. |
| 2 | Independently probe workloads and host visibility | Applications healthy → control-plane-only impact possible. Visibility also lost → RB-014 and owner escalation. |
| 3 | Gateway status versus bounded daemon/service state | Gateway bad/daemon alive → H1/H2. Daemon down → 4. Missing discriminating tool → keep both. |
| 4 | Docker/containerd unit journal and recent config | Startup/config/runtime error supports H3/H4/H6; sanitized fields only. |
| 5 | Host memory/filesystem/I/O and boot | Resource cause → RB-007/005/010; repeated restart without capacity repair likely recurs. |
| 6 | Owner assesses workload/live-restore/restart impact | Capture evidence; no model daemon restart. Verify both control and data planes after owner repair. |

## Decision tree

```text
single target refused/missing? -> policy/identity
multiple runtime reads fail -> workloads independently healthy?
  gateway fails, daemon healthy -> gateway/network/auth
  daemon service fails -> config/resources/runtime logs
  no independent evidence -> insufficient_evidence; platform escalation
```

## Evidence interpretation

Live restore can keep containers running while the daemon is unavailable, subject to configuration and documented limitations. Do not assume it is enabled or makes daemon restart risk-free. [Docker live restore](https://docs.docker.com/engine/daemon/live-restore/)

## False positives and edge cases

Expired gateway credential, route deny, tunnel outage, API version mismatch, one removed container, stale inventory, busy daemon, host reboot and healthy processes with unavailable inspection.

## Diagnosis outcome

All common outcomes allowed. Probable daemon failure requires independent service/runtime evidence; gateway failure alone supports only a control-path hypothesis. Missing mandatory metrics keeps the existing undiagnosable behavior.

## Mitigation

Platform owner restores the specific gateway/transport/config or host resource. Daemon restart is an exceptional host-wide operator action after impact assessment; container restart cannot repair an unavailable daemon control path.

## Recovery

Allowlisted runtime reads work consistently, intended container identities/states are accounted for, and workload endpoints are healthy. API availability alone does not establish workload recovery.

## Root-cause correction

Repair runtime configuration/resource limits, storage fault, credential rotation or version compatibility; test upgrade/live-restore behavior in a matching lab.

## Action safety

Daemon/containerd restart, gateway restart and runtime config/storage changes are `MUTATING_HIGH_RISK`. Require exact host/unit/config, full workload impact inventory, protected databases/control plane, capacity repair, rollback and owner authority. Block unknown live-restore behavior, unresolved storage corruption, unavailable audit, missing service tool or hypothetical target scope. Current Argus must escalate; registering restart_container does not authorize restarting Docker.

## Human-in-the-Loop

Approval must describe every affected workload, outage/state-loss risks, exact unit/change and recovery plan. A daemon restart cannot be approved as if it affected only one container.

## Forbidden actions

`FORBIDDEN`: direct Docker socket access, unauthenticated daemon exposure, remove `/var/lib/docker`, purge storage-driver data, arbitrary systemctl/shell, repeated daemon restarts or recreate all containers blindly.

## Evidence preservation

Bounded runtime journal and gateway errors, host resource state, config fingerprints and independent workload inventory in a healthy evidence sink. Record inability to obtain a Docker snapshot; do not fabricate it.

## Verification

After owner repair, three fresh independent gateway/daemon reads and at least 5 minutes of stable workload probes. Confirm API version/identities, no fresh startup/storage errors, no unexpected container losses and healthy resources. Partial inventory, unknown workload state or recurrence prevents closure; no automatic second restart.

## Rollback

Platform owner retains previous compatible runtime config/version; downgrade/storage rollback can be unsafe and requires its own tested procedure. Restart itself is not reversible; there is no automatic daemon rollback capability.

## Escalation

Platform/runtime owner immediately, storage owner for driver/I/O errors, incident commander if host-wide impact. Attach exact path/category, independent service state, resources, protected workloads and uncertainty. Stop when execution outcome cannot be determined.

## Recording / memory

Common record plus control-versus-data-plane impact, gateway/daemon versions, live-restore evidence, affected workload inventory and owner action outcome.

## Prevention / follow-up

Independent gateway/runtime health, tested upgrade/restart procedure, bounded journals, credential lifecycle and per-host recovery inventory.

## Lab validation

Dedicated disposable VM: first stop only the read gateway for 90 seconds while a synthetic API remains serving. Expect a control-path failure, insufficient daemon attribution without status tool and zero container/daemon writes. Restore gateway; separately test a reviewed bad daemon-config fixture only on a snapshot-restorable VM with out-of-band access and saved workload state. Owner restores the exact config; denial/absent restart capability must block agent restart. Verify API and workloads for 5 minutes, preserve all lifecycle artifacts, and restore snapshot on abort. No runtime service was changed for this library.

## References

- [Docker daemon troubleshooting](https://docs.docker.com/engine/daemon/troubleshoot/), [live restore](https://docs.docker.com/engine/daemon/live-restore/).
- [systemd journalctl manual source](https://raw.githubusercontent.com/systemd/systemd/main/man/journalctl.xml), [systemctl manual source](https://raw.githubusercontent.com/systemd/systemd/main/man/systemctl.xml). The rendered freedesktop pages could not be fetched; official source manuals were reviewed instead.

## Argus capability gaps

### Missing telemetry

Independent gateway/daemon/unit state, complete workload impact inventory and runtime config/version history.

### Missing tools

`get_runtime_gateway_status`, `get_docker_daemon_status`, `get_service_state`; separately reviewed `restart_service` if ever enabled.

### Tool improvements

Preserve transport/auth/policy/runtime distinctions and independent host-probe availability; don't hide journal failures.

### Detector improvements

Multi-target control-path detector plus scope/host-wide policy, without bypassing RB-014 guards.
