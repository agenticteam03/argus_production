# T-0035 — A monitoring heartbeat per host: Argus notices when it stops seeing a host, and resolves nothing meanwhile

| Field | Value |
|---|---|
| Status | `in progress` — step 1 (code, offline) done 2026-10-12; step 2 (the VMs) next |
| Phase | 13 — "Prometheus down on one host" (T-0032's "not covered") ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | [ACR-0009](../../architecture/changes/ACR-0009-monitoring-heartbeat.md), accepted in #108 (`juanbetancurm`); applied here: `ARCHITECTURE.md` 1.8.8 (§6.4, §7.3) |
| Branch | `task/T-0035-monitoring-heartbeat` (from `main`) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | step 2 only (both: the rule on both hosts' Prometheus, vm-095's scheduler and migration) |

## Goal (plain language)

When a host's monitoring stops (its Prometheus, its Alertmanager, or the path to Argus), nobody is told, its alerts
expire and Argus records them as resolved. With this task each host sends a heartbeat through the alert path Argus
already reads; a lost heartbeat opens one escalated "Host monitoring unavailable" incident per episode (no run, no
model), and while a host has no fresh heartbeat Argus resolves nothing on it.

## Design (as ACR-0009, with `juanbetancurm`'s three notes of #108)

- **Rule** (`deploy/monitoring/alerts.yml`, both hosts): `ArgusMonitoringHeartbeat`,
  `count by (argus_host) (up{argus_host!=""}) > 0`, no `for`.
- **`AlertNotification.updated_at`**: the adapter reads Alertmanager's `updatedAt`.
- **`application/monitoring.py` — `MonitoringWatch.observe(host, active)`** on every reconcile tick: fresh = listed
  with the host's `argus_host`, `endsAt` in the future, `updatedAt` within `stale_after` (a kept copy that is not
  renewed is not fresh: note 1's important test). States `starting` → `alive` (two consecutive fresh ticks: note 2,
  also to leave the grace) → `lost` (no renewal for `stale_after`, or none within `grace`) → `alive` (two fresh ticks,
  audited `monitoring.recovered`).
- **Lost** → one incident per episode, `monitoring:<host>:<episode start>`, host target, `monitoring_blind_spot`,
  finding "Host monitoring unavailable", RB-014, stored already `escalated` / `undiagnosable` (a worker only claims
  `queued`); the cause from what was observed plus one bounded `GET /-/ready` of the host's Prometheus (3 s).
- **No resolution without a fresh heartbeat**: `observe` returns True on any tick without one (lost or not yet);
  `ReconcileFiringAlerts` then skips `resolve_absent` (`"heartbeat not fresh"` / `"monitoring lost"` in its counts).
  The ACR says "while its heartbeat is not fresh"; a first version that only stopped once lost resolved an
  application incident in the minutes before the loss was declared (caught by note 3's test).
- **The heartbeat never reaches intake** (`HandleAlertNotification` ignores it by `alertname`: push and pull).
- **State per host** in the store (`monitoring_state`, migration 006, both stores): a restart keeps a lost episode
  (no second incident) and starts a new grace otherwise.
- **Maintenance**: `argus monitoring maintenance <host> --minutes N --as <who>` (1..240, audited); a loss in it is
  audited `monitoring.lost_in_maintenance`, no incident; one still present after it ends opens its incident.
- **Configuration**: `reconcile_firing_alerts.monitoring_heartbeat` in `deploy/scheduler/schedules.yaml`
  (`enabled`, `stale_after_s` ≥ two ticks, `grace_s` ≥ `stale_after_s`). Step 1 shipped it `enabled: false`; step 2
  turned it on once the rule ran on both hosts. **The AFTER-MERGE of this PR must recreate `argus-v18-prometheus` on
  both hosts** (the rule file is bind-mounted): a scheduler with the check on and a Prometheus without the rule would
  stop every resolution and, after the grace, open a loss incident per host.

## Tests

`tests/test_t0035_monitoring_heartbeat.py`, 21 tests (red seen: no `argus.application.monitoring`): fresh / kept but
not renewed / expired / another host's; a loss opens one escalated incident with no run and the observed cause;
Alertmanager unreachable; one incident per episode across a scheduler restart; two fresh ticks to recover and a later
loss is a new episode; one late fresh tick does not end the grace; never seen after the grace; a queued application
incident stays open (and nothing resolves before the loss is declared), then resolves after recovery; the heartbeat
never reaches intake; maintenance opens nothing and expires; maintenance bounds; the rule; the adapter reads
`updatedAt`; the configuration (off in the shipped file) and the command. `tests/test_postgres.py`: the state and the
escalated incident under the runtime role (runs where `ARGUS_TEST_PG_OWNER_DSN` is set: CI).

## Steps

1. **Code (offline)** — done 2026-10-12 on the branch.
2. **The VMs (both leases):** migration 006 on vm-095; both hosts' Prometheus reload the rule; vm-095's scheduler
   (and agent, worker) rebuilt; **measure the real `updatedAt` renewal and `endsAt`** on Alertmanager 0.34.0 (note 1)
   before turning the check on; then `monitoring_heartbeat.enabled: true`.
3. **Verification (as T-0032, note 3):** with an application incident of vm-166 queued, stop vm-166's Prometheus:
   one incident per episode, the application incident stays open, recovery after two ticks; separately its
   Alertmanager; vm-095 unaffected; NO INTERFERENCE.
