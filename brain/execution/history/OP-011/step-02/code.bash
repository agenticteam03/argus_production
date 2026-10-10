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
# OP-011 step 02 — alert correlation on the VMs: SC-03 on vm-166 must give ONE incident (2026-10-09, conantkd).
# WHY: step 01 implemented ARCHITECTURE §6.4 (a second alert on the same target and class is attached, not a new
#   incident). Done when SC-03, which fires DependencyProbeFailed and ContainerUnhealthy on argus-lab-api, opens one
#   incident with two alert occurrences (started + attached), and the next passes say duplicate.
# PRE: branch task/OP-011-correlation pushed (it is stacked on task/T-0024-sc05-disk, which both VMs run now);
#   the session lease is ours (brain.py start).
# MUTATES: vm-095: a Postgres backup, migration 004 (CREATE TABLE alert_occurrence, additive), the agent image
#   (agent, worker, scheduler recreated). vm-166: checkout only (no service of vm-166 changes). Lab: cache stopped
#   then started; incident rows.
# ROLLBACK: deploy.sh task/T-0024-sc05-disk on both VMs + rebuild agent/worker/scheduler on vm-095 (that code never
#   reads alert_occurrence, so the table can stay; to remove it: DROP TABLE alert_occurrence and
#   DELETE FROM schema_migrations WHERE version = '004_alert_occurrence', as argus_owner).
# =====================================================================================

# --- S.1 [VM vm-095 and vm-166 · bash] state probe (read-only) ---------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^ref=|^commit=|LAB BASELINE'
sudo docker ps --format '{{.Names}} {{.Status}}' | grep argus-v18- | sort
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# expected: both on task/T-0024-sc05-disk b049086 (or 22a924d), LAB BASELINE OK, NO INTERFERENCE

# --- S.2 [VM vm-095 · bash] backup, deploy, migrate, rebuild -----------------------------------------------------------
ME=conantkd
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME | tail -1                          # BACKUP OK
sudo bash /opt/argus-v18/app/ops/deploy.sh task/OP-011-correlation --as $ME | tail -1           # DEPLOY OK
sudo bash /opt/argus-v18/app/ops/db-migrate.sh | tail -1                # schema: 001_init, 002_checkpoints, 003_worker_lease, 004_alert_occurrence
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler 2>&1 | grep -E 'Recreated|Started|Error' | tail -4; cd ~
sudo docker logs --since 2m argus-v18-scheduler 2>&1 | grep -E "reconcile|Traceback" | tail -3

# --- S.3 [VM vm-166 · bash] same ref (checkout only) ---------------------------------------------------------------------
ME=conantkd
sudo bash /opt/argus-v18/app/ops/deploy.sh task/OP-011-correlation --as $ME | tail -1           # DEPLOY OK

# --- S.4 [VM vm-166 · bash] SC-03: stop the cache, wait for both alerts --------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo docker stop argus-lab-cache
# poll http://127.0.0.1:18091/api/v2/alerts?active=true until DependencyProbeFailed AND ContainerUnhealthy fire
#   (every 10 s, max 5 min)

# --- S.5 [VM vm-095 · bash] one incident, two occurrences ----------------------------------------------------------------
# inside argus-v18-worker: make_store(Settings()) → the alert-triggered incidents on vm-166/container:argus-lab-api
#   opened since S.4, their alert_occurrences(id), evidence_state(id); wait until it is closed or escalated
#   (every 15 s, max 7 min). Expected: ONE incident, occurrences [started, attached], evidence version 2, DIAGNOSED.
sudo docker logs --since 8m argus-v18-scheduler 2>&1 | grep -E "reconcile firing|attached" | tail -6
#   expected: one pass with {'started': 1, 'attached': 1}, then {'duplicate': 2}

# --- S.6 [VM vm-166 · bash] reset ----------------------------------------------------------------------------------------
sudo docker start argus-lab-cache
# poll until no alert is active; then
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep "LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# and on vm-095: no new incident on argus-lab-api after S.5; nonint-check after
