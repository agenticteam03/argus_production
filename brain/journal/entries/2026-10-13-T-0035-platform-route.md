## 2026-10-13 — T-0035: a monitoring loss takes the `platform` route of routing.yaml

Type: fix
Who: conantkd (+ agent)
Context: #127 review (`juanbetancurm`): the loss notification of T-0035 (`argus/application/monitoring.py`) still sent
the fixed `channel:operators`; its comment said it would take the `platform` family's route once `routing.yaml`
(T-0042) was merged, and it was.
Decision / result: `MonitoringWatch` takes the validated `Routing` and routes a loss by the family of
`monitoring_blind_spot` (`platform`), else the default. `load_routing` (wiring) reads `routing.yaml` for the agent and
the scheduler alike (fail closed: an invalid file stops the scheduler as it stops the agent). Today's file has no
`by_family` entry, so the route on the VMs stays `channel:operators`.
Consequences: vm-095's scheduler gets it at the next AFTER-MERGE; no migration, no Prometheus change.
References: [task](../../tasks/current/T-0035-monitoring-heartbeat.md).

### Test state

`tests/test_t0035_monitoring_heartbeat.py`: 3 new tests (red seen): the `platform` route, the default when only
another family has one, and `load_routing` (a file with a `platform` route, no file, an unknown family refused).

### Next step

PR (reviewer `juanbetancurm`); the VMs get it at the next AFTER-MERGE.
