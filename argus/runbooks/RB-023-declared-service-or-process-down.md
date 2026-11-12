# RB-023 — Declared systemd unit or host process not running

## Metadata

```yaml
id: RB-023
title: Declared systemd unit or host process not running
status: draft
owner: Argus Team
version: 1.0.0
created: 2026-10-30
last_reviewed: 2026-10-30
source_review_date: 2026-10-30
last_tested: null
detector: target_down
```

## Scope

A `service` target (a systemd unit `<name>.service`) or a `process` target (a host process found by its command name or a
pidfile) declared in the inventory ([ACR-0044](../../brain/architecture/changes/ACR-0044-live-targets.md)). Containers are
out of scope (RB-001, RB-002, RB-008). Apply [shared contracts](RUNBOOK-CONVENTIONS.md).

## Incident definition

The host probe says the target is on the host (`target_present` = 1: the unit file is installed, or the process is
declared) and does not run (`target_up` = 0: no process in the unit's cgroup, or no process with that command name or
pidfile pid). A target that is not on the host (present 0) or whose presence is unknown is never this incident.

## User / service impact

Whatever the unit or process provides is not being done (a scheduled job, a sync, a local service). The impact on users
is unknown until the owner says what depends on it.

## Trigger / detection conditions

Alert `TargetDown`: `argus_target_up{kind=~"service|process"} == 0 and on(argus_host,kind,name) argus_target_present == 1`
for 1 minute. The detector re-reads both signals: unknown is not down.

## Symptoms

The map shows the box `stopped`; the target list marks it "(stopped)"; the work the unit or process does has stopped.

## Plausible causes / hypotheses

H1 the process exited or crashed (and systemd gave up restarting it); H2 it was stopped on purpose (maintenance); H3 it
never started after a reboot (unit disabled); H4 a one-shot or timer-driven unit that is idle between runs (a false
positive: declare the timer, not the service); H5 a pidfile left by a process that died, or a `comm` that changed with a
new version (an observation gap, not a failure).

## Required evidence

The unit's installed/active state and the pids in its cgroup, or the declared process's pids, state and memory; the
host's memory and CPU at the time (an OOM or a saturated host can kill or starve it).

## Required Argus tools

| Tool / input | Purpose / output | Safety class |
|---|---|---|
| `get_service_status(target)` | Unit installed, running, pids in its cgroup | `READ_ONLY_SAFE` |
| `get_process_status(target)` | Running or not, pids, state, memory (never the command line) | `READ_ONLY_SAFE` |
| `get_host_memory(host)` / `get_host_cpu(host)` | Host pressure at the time | `READ_ONLY_SAFE` |

## Missing tools

The unit's exit status, restart count and recent journal lines (systemd's `NRestarts`, `ExecMainStatus`) need D-Bus or
the journal; `host.journal` reads allowlisted units only. Proposed later, not in this class.

## Diagnostic workflow

1. Read the evidence pack (the unit or process, the host's memory and CPU).
2. If the host is under memory pressure, check `host.kernel_oom_records` by hand (RB-007 / RB-001 reasoning).
3. Ask the owner whether it was stopped on purpose.
4. Escalate with the evidence; Argus claims no diagnosis.

## Decision tree

- Present 0 → not this incident (the unit was removed or never installed).
- Present 1, up 0, host memory pressure → suspect an OOM kill; escalate with the host evidence.
- Present 1, up 0, host normal → the owner decides (crash, stop, disabled).

## False positives and edge cases

A timer-driven or one-shot unit is idle between runs: declare the `.timer` as the target instead. A unit with
`Delegate=` keeps its processes in sub-cgroups, which still name the unit. A pidfile whose pid was reused reads as running.

## Diagnosis outcome

`escalated` with the evidence pack (strategy `evidence_pack`): no diagnosis is claimed.

## Mitigation and action safety

No write is offered: `systemctl` actions are not in the action catalogue. A restart is a human action on the host.

## Recovery and verification

After the owner's action, `target_up` returns to 1 and the alert resolves; the map shows the box `running`.

## Recording / escalation

Record the unit or process, the time it stopped (the alert's start), the host evidence and the owner's answer.

## Lab validation

Not tested: declare a unit on a lab host, stop it, and expect `TargetDown`, the incident `target_down`, the evidence pack
and an escalation; start it again and expect the alert to resolve.
