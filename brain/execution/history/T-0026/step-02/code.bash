# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
#   [VM vm-095 · bash]      ssh argus-vm095
#   [VM vm-166 · bash]      ssh argus-vm166
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated".
# =====================================================================================

# =====================================================================================
# T-0026 step 02 — resolved alerts on the VMs: SC-03's alerts resolve when the cache is back (2026-10-09, conantkd,
#   session f94089c29baa). Run by the agent over SSH.
# WHY: step 01 implemented §6.4 "Resolution" (ACR-0005): in this pull deployment an occurrence resolves when its alert
#   is absent from a successful read of the host's active alerts. Done when SC-03 opens one incident with two
#   occurrences and, after the cache is started again, the next passes mark both `resolved` (audit
#   incident.alert_resolved ×2 and incident.alerts_all_resolved), with the concluded incident unchanged.
# PRE: branch task/T-0026-alert-resolution pushed (stacked on task/OP-011-correlation, which both VMs run: cb300df);
#   the session lease is ours (brain.py start).
# MUTATES: vm-095: a Postgres backup, migration 005 (ADD COLUMN resolved_at, a trigger, a column grant: additive), the
#   agent image (agent, worker, scheduler recreated). vm-166: checkout only. Lab: cache stopped then started;
#   incident and occurrence rows.
# ROLLBACK: deploy.sh task/OP-011-correlation on both VMs + rebuild agent/worker/scheduler on vm-095 (that code never
#   reads resolved_at and never updates an occurrence, so migration 005 can stay; to remove it, as argus_owner:
#   DROP TRIGGER alert_occurrence_resolve_only ON alert_occurrence; DROP FUNCTION argus_alert_occurrence_resolve_only();
#   REVOKE UPDATE (status, resolved_at) ON alert_occurrence FROM argus_runtime;
#   ALTER TABLE alert_occurrence DROP COLUMN resolved_at; DELETE FROM schema_migrations WHERE version = '005_alert_resolution').
# NOTE: `docker compose` reads stdin: every command in a `bash -s` script gets </dev/null.
# =====================================================================================

# --- S.1 [VM vm-095 and vm-166 · bash] session marker and state probe (read-only) ----------------------------------------
echo 'holder=conantkd session=f94089c29baa' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^ref=|^commit=|LAB BASELINE'
sudo docker ps --format '{{.Names}} {{.Status}}' | grep argus-v18- | sort
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# expected: both on task/OP-011-correlation cb300df, LAB BASELINE OK, NO INTERFERENCE

# --- S.2 [VM vm-095 · bash] backup, deploy, migrate, rebuild, db check ---------------------------------------------------
ME=conantkd
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1                    # BACKUP OK
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0026-alert-resolution --as $ME </dev/null | tail -1  # DEPLOY OK
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | tail -1                                    # … 005_alert_resolution
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E 'Recreated|Started|Error' | tail -4; cd ~
sudo docker exec argus-v18-worker python -m argus db check </dev/null | tail -8                       # 5 new lines, all ok

# --- S.3 [VM vm-166 · bash] same ref (checkout only), then SC-03 ---------------------------------------------------------
ME=conantkd
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0026-alert-resolution --as $ME </dev/null | tail -1  # DEPLOY OK
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo docker stop argus-lab-cache </dev/null
# poll http://127.0.0.1:18091/api/v2/alerts?active=true until DependencyProbeFailed AND ContainerUnhealthy fire
#   (every 10 s, max 5 min)

# --- S.4 [VM vm-095 · bash] one incident, two firing occurrences ---------------------------------------------------------
# inside argus-v18-worker: the alert-triggered incidents on vm-166/container:argus-lab-api opened since S.3 with
#   alert_occurrences(id); wait until the incident is concluded and both occurrences exist (every 15 s, max 7 min).

# --- S.5 [VM vm-166 · bash] the cache comes back --------------------------------------------------------------------------
sudo docker start argus-lab-cache </dev/null
# poll until no alert is active on vm-166's Alertmanager (every 10 s, max 5 min)

# --- S.6 [VM vm-095 · bash] both occurrences resolved, the incident unchanged --------------------------------------------
# wait one more reconciliation pass (60 s); then the same probe: both occurrences `resolved` with resolved_at, the
#   incident's status/outcome as in S.4, audit incident.alert_resolved ×2 + incident.alerts_all_resolved
#   (closed: false). Scheduler log: a pass with 'resolved'.
sudo docker logs --since 10m argus-v18-scheduler 2>&1 | grep -E "reconcile firing|resolved" | tail -6

# --- S.7 [VM vm-095 and vm-166 · bash] baseline -------------------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^commit=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
