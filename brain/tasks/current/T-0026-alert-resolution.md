# T-0026 — Resolved alerts (§6.4 "Resolution", ACR-0005)

| Field | Value |
|---|---|
| Status | `in progress` — step 1 (code, tests) done; step 2 (VMs) next |
| Phase | 7 — alerting ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)); follows OP-011 (correlation) |
| Architecture | [ACR-0005](../../architecture/changes/ACR-0005-pull-alert-resolution.md) (1.8.4 → 1.8.5): §6.4 "Resolution", §7.3, §8.1 |
| Branch | `task/T-0026-alert-resolution`, on top of `task/OP-011-correlation` (uses its `alert_occurrence` table) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | step 2: migration 005 and the agent image on vm-095, SC-03 on vm-166 |

## Goal (plain language)

When an alert stops, Argus must notice it. Each alert occurrence of an incident gets its own status (`firing` →
`resolved`). This deployment pulls alerts, so a resolved alert is one that is no longer listed by its host's
Alertmanager in a read that worked (a silenced alert is still listed: silencing is not resolving). When every alert of
an incident has stopped and no worker has started on it yet, the incident closes `resolved_externally` without spending
an investigation. A running investigation finishes; a concluded incident is never changed.

## Decisions (2026-10-09, `conantkd` + agent)

- Pull resolution = absence from a successful read of **every active alert** (`silenced=true&inhibited=true`), not
  from the firing read; only occurrences recorded before that read are judged; an unreadable host resolves nothing.
- When all resolve: queued → closed `resolved_externally` (a conditional update, so a worker that claimed it first
  wins); running → audit only; concluded → audit only.
- The webhook takes `endsAt` as the resolution time; the pull uses the time of the read.
- The runtime role may update only `status` and `resolved_at` of `alert_occurrence`, only `firing → resolved`
  (migration 005, column grant + trigger); `argus db check` proves it.

## Steps

1. **Code and tests** (done 2026-10-09): `tests/test_t0026_alert_resolution.py` (red seen: a `resolved` notification
   was `ignored`, `active_alerts` and `resolve_absent` missing), `tests/test_postgres.py::test_alert_occurrence_resolution`,
   five new `argus db check` lines.
2. **VMs:** backup, migration 005 and the agent image on vm-095; `argus db check`; SC-03 on vm-166: stop the cache,
   the incident opens (two occurrences), start the cache, the next passes resolve both occurrences
   (`incident.alert_resolved`, `incident.alerts_all_resolved`); NO INTERFERENCE.

## Done when

SC-03 on vm-166 ends with both occurrences `resolved`, the concluded incident unchanged, and the audit events present.
