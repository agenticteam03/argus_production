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
# T-0027 step 02 — the monitoring blind spot on the VMs: node-exporter stopped on vm-166 opens a monitoring_blind_spot
#   incident from the pulled alert (2026-10-09, conantkd, session f94089c29baa). Run by the agent over SSH.
# WHY: step 01 registered the class (RB-014, evidence_pack), its signal and the alert ArgusScrapeTargetDown. Done when
#   the pulled alert's incident on vm-166/host:vm-166 is escalated as monitoring_blind_spot with the evidence pack and
#   no model call, and its occurrence is resolved after the exporter is back (T-0026).
# PRE: branch task/T-0027-blind-spot pushed (stacked on task/T-0026-alert-resolution, which both VMs run: ea01c68);
#   the session lease is ours.
# MUTATES: vm-095: the agent image (agent, worker, scheduler recreated), argus-v18-prometheus recreated (new rule).
#   vm-166: argus-v18-prometheus recreated (new rule); argus-v18-node-exporter stopped then started. No migration.
# ROLLBACK: deploy.sh task/T-0026-alert-resolution on both VMs + rebuild agent/worker/scheduler on vm-095 + recreate
#   argus-v18-prometheus on both (the old rule file); `docker start argus-v18-node-exporter` if it is still stopped.
# NOTE: `docker compose` reads stdin: every command in a `bash -s` script gets </dev/null.
# =====================================================================================

# --- S.1 [VM vm-095 · bash] deploy, rebuild the agent, reload Prometheus' rules ------------------------------------------
ME=conantkd
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0027-blind-spot --as $ME </dev/null | tail -1        # DEPLOY OK
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E 'Started|Error' | tail -3
cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file vm-095.env -f compose.monitoring.yml -f compose.core-join.yml up -d --force-recreate --no-deps argus-v18-prometheus </dev/null 2>&1 | tail -1; cd ~
sudo docker exec argus-v18-prometheus wget -qO- http://localhost:9090/api/v1/rules </dev/null | grep -c ArgusScrapeTargetDown   # >= 1

# --- S.2 [VM vm-166 · bash] same ref, reload Prometheus' rules, stop node-exporter ---------------------------------------
ME=conantkd
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0027-blind-spot --as $ME </dev/null | tail -1        # DEPLOY OK
cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file vm-166.env -f compose.monitoring.yml -f compose.loopback.yml up -d --force-recreate --no-deps argus-v18-prometheus </dev/null 2>&1 | tail -1; cd ~
sudo docker exec argus-v18-prometheus wget -qO- http://localhost:9090/api/v1/rules </dev/null | grep -c ArgusScrapeTargetDown   # >= 1
sudo docker stop argus-v18-node-exporter </dev/null
# poll vm-166's Alertmanager until ArgusScrapeTargetDown fires (every 10 s, max 6 min)

# --- S.3 [VM vm-095 · bash] the incident ---------------------------------------------------------------------------------
# inside argus-v18-worker: the alert incidents on vm-166/host:vm-166 since S.2: class monitoring_blind_spot, escalated,
#   evidence host.memory + host.cpu, no model call; its occurrence firing.

# --- S.4 [VM vm-166 · bash] node-exporter back ---------------------------------------------------------------------------
sudo docker start argus-v18-node-exporter </dev/null
# poll until no alert is active (every 10 s, max 5 min)

# --- S.5 [VM vm-095 · bash] resolved -------------------------------------------------------------------------------------
# after one more pass: the occurrence resolved (absent_from_pull), the incident unchanged.

# --- S.6 [VM vm-095 and vm-166 · bash] baseline --------------------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^commit=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
