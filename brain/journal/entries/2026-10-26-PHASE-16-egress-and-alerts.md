## 2026-10-26 - PHASE-16: security alerts to the team's Telegram group; the scheduler's egress proxy

Type: implementation
Who: conantkd (+ agent)
Context: the two step 5 follow-ups left in phase 16: OCI-only egress for the scheduler was not enforced, and security
events (ACR-0018 §18) reached no person. conantkd chose a Telegram group as the team's route.
Decision / result:
- `SecurityAlerts` (`infrastructure/security_alerts.py`, `security_alerts` in `schedules.yaml`): every minute the
  scheduler posts each new alerting audit row to vm-095's Alertmanager with `argus_security="true"`; the alert names
  the event, the actor, the time and the audit id, never the detail. A restart looks back one hour; a repeat merges in
  Alertmanager. Argus's intake skips those alerts.
- `alertmanager-vm-095.yml` (mounted by `compose.core-join.yml`): host alerts still pulled; the security route goes to
  Telegram with the token and the chat id read from files under `/opt/argus-v18/secrets/alertmanager/`.
- `argus-v18-egress` (tinyproxy, built from alpine 3.20): CONNECT :443 to `objectstorage.<region>.oraclecloud.com` and
  `api.telegram.org` only. The scheduler moves to `argus-v18-sched` (internal); Postgres, the tunnel, vm-095's
  Prometheus and Alertmanager join it.
- ACR-0018 §18 phase 16 reading, ARCHITECTURE 1.8.37, `policies/NETWORK.md`.
Consequences: after the deploy (Postgres and the tunnel are recreated to join the new network; a backup first), phase
16 is done. A new destination in the proxy's filter needs an ACR.
References: ACR-0018 §18, [task](../../tasks/current/PHASE-16-operator-access.md).

### Test state

`tests/test_phase16_security_alerts.py` (the job, the intake skip, the schedule entry, the compose files, the proxy
filter, the Telegram route) and the full suite pass locally.

### Next step

juanbetancurm reviews; then the deploy on vm-095: the bot token on the VM, the chat id read with `getUpdates`, the
images, and the checks (OCI through the proxy, any other destination refused, a test alert reaching the group).
