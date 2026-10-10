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
# T-0028 step 02 — SC-06 on the VMs: a burner throttled at its 0.3-core quota on vm-166 (2026-10-09, conantkd,
#   session d550d6afba41). Run by the agent over SSH.
# WHY: step 01 registered cpu_saturation (RB-006, the container trigger), its signal and ContainerCpuThrottled, and the
#   gateway's cpu_limit_cores. Done when the pulled alert opens a cpu_saturation incident on
#   vm-166/container:argus-lab-burner that the model DIAGNOSES naming the quota, and the burner is gone afterwards.
# PRE: task/T-0028-vm-proof pushed (task/T-0027-blind-spot, which both VMs run, + task/T-0028-sc06-cpu); the lease.
# MUTATES: vm-095: the agent image (agent, worker, scheduler), argus-v18-prometheus recreated (rules). vm-166: the
#   target services rebuilt (gateway, exporter, probes: service.py and vm-166.json), argus-v18-prometheus recreated;
#   the lab container argus-lab-burner started then removed. No migration.
# ROLLBACK: deploy.sh task/T-0027-blind-spot on both VMs; rebuild vm-095's agent/worker/scheduler and vm-166's target
#   services; recreate argus-v18-prometheus on both; `docker rm -f argus-lab-burner` on vm-166.
# NOTE: `docker compose` reads stdin: every command in a `bash -s` script gets </dev/null.
# =====================================================================================

# --- S.2 [VM vm-095 · bash] deploy, agent image, Prometheus rules ------------------------------------------------------
ME=conantkd
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0028-vm-proof --as $ME </dev/null | tail -1        # DEPLOY OK
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E 'Started|Error' | tail -3
cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file vm-095.env -f compose.monitoring.yml -f compose.core-join.yml up -d --force-recreate --no-deps argus-v18-prometheus </dev/null 2>&1 | tail -1; cd ~

# --- S.3 [VM vm-166 · bash] deploy, target services, Prometheus rules, start the burner ----------------------------------
ME=conantkd
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0028-vm-proof --as $ME </dev/null | tail -1        # DEPLOY OK
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml up -d --build </dev/null 2>&1 | grep -E 'Recreated|Error' | tail -6
cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file vm-166.env -f compose.monitoring.yml -f compose.loopback.yml up -d --force-recreate --no-deps argus-v18-prometheus </dev/null 2>&1 | tail -1
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc06 up -d argus-lab-burner </dev/null 2>&1 | tail -1; cd ~
# poll vm-166's Alertmanager until ContainerCpuThrottled fires (every 15 s, max 10 min)

# --- S.4 [VM vm-095 · bash] the incident ----------------------------------------------------------------------------------
# inside argus-v18-worker: the alert incident on vm-166/container:argus-lab-burner: cpu_saturation, DIAGNOSED,
#   diagnosis naming the quota, root cause the burner.

# --- S.5 [VM vm-166 · bash] remove the burner -----------------------------------------------------------------------------
sudo docker rm -f argus-lab-burner </dev/null
# poll until no alert is active; then the occurrence resolved (T-0026)

# --- S.6 [VM vm-095 and vm-166 · bash] baseline ---------------------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^commit=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
