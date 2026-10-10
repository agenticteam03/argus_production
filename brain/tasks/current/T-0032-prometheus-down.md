# T-0032 — Phase 13: Prometheus down on one host escalates that host only

| Field | Value |
|---|---|
| Status | `done` 2026-10-10 (vm-095's Prometheus stopped about 2 min: vm-095 UNDIAGNOSABLE, vm-166 HEALTHY, no restart) |
| Phase | 13 — failure and recovery ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md): "partition ⇒ escalation for one host only") |
| Architecture | no change (G-007: unknown is never healthy; each host is read through its own Prometheus) |
| Branch | `task/T-0032-prometheus-down`, from `main` |
| Owner | `conantkd` (+ agent) |

## Goal (plain language)

If the monitoring of one host is lost, Argus must say "I cannot see it" for that host, never "healthy", and go on
answering for the other host.

## Found

Nothing to fix: both runners already catch `MetricsUnavailable` and end the incident `undiagnosable` before any model
call, and the real Prometheus adapter turns a refused connection into `MetricsUnavailable` per host.

## Steps

1. **Tests** (done): `tests/test_t0032_prometheus_down.py` (3; red seen by removing the handling in each runner).
2. **vm-095** (done, [evidence](../../execution/history/T-0032/step-02/evidence.md)): Prometheus stopped 16:25–16:27
   UTC; vm-095 check UNDIAGNOSABLE (`ConnectError`), vm-166 check HEALTHY, restarts 0, vm-095 HEALTHY again after the
   start; LAB BASELINE OK, NO INTERFERENCE. Lease vm-095 only (monitoring, not the agent).

## Not covered

- No alert fires while a host's own Prometheus is down (`ArgusScrapeTargetDown` runs in that Prometheus). A watcher
  from the other host, or a dead-man alert, is a follow-up.
- vm-166's Prometheus or the tunnel down (needs the vm-166 lease); executor token rotation.
