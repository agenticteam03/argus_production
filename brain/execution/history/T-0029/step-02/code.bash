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
# T-0029 step 02 — SC-08 on the VMs: nginx in front of a slow upstream on vm-166 (2026-10-10, conantkd, session
#   d550d6afba41). Run by the agent over SSH.
# WHY: step 01 added the exporter's HTTP probe (502/504 = gateway error), nginx_upstream_failure (RB-015) and
#   HttpGatewayErrors. Done when the pulled alert opens a nginx_upstream_failure incident on
#   vm-166/container:argus-lab-nginx, DIAGNOSED naming argus-lab-slow, with no alert from the api's probe.
# PRE: task/T-0029-vm-proof pushed (task/T-0028-vm-proof, which both VMs run, + task/T-0029-sc08-nginx); the lease.
# MUTATES: vm-095: agent, worker, scheduler recreated; argus-v18-prometheus recreated (rules). vm-166: target services
#   rebuilt (the exporter's probe, vm-166.json), argus-v18-prometheus recreated; argus-lab-nginx and argus-lab-slow
#   started then removed (profile sc08; pulls nginx:1.27-alpine). No migration.
# ROLLBACK: deploy.sh task/T-0028-vm-proof on both VMs; rebuild vm-095's agent/worker/scheduler and vm-166's target
#   services; recreate argus-v18-prometheus on both; `docker compose --profile sc08 down` in deploy/lab on vm-166.
# NOTE: `docker compose` reads stdin: every command in a `bash -s` script gets </dev/null.
# =====================================================================================

# --- S.1 [VM vm-095 · bash] deploy, agent processes, Prometheus rules ----------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0029-vm-proof --as conantkd </dev/null | tail -1
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --force-recreate --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E 'Started|Error' | tail -3
cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file vm-095.env -f compose.monitoring.yml -f compose.core-join.yml up -d --force-recreate --no-deps argus-v18-prometheus </dev/null 2>&1 | tail -1; cd ~

# --- S.2 [VM vm-166 · bash] deploy, target services, Prometheus rules, SC-08 up ------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0029-vm-proof --as conantkd </dev/null | tail -1
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml up -d --build </dev/null 2>&1 | grep -E 'Recreated|Error' | tail -6
cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file vm-166.env -f compose.monitoring.yml -f compose.loopback.yml up -d --force-recreate --no-deps argus-v18-prometheus </dev/null 2>&1 | tail -1
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc08 up -d argus-lab-slow argus-lab-nginx </dev/null 2>&1 | tail -2; cd ~
# poll vm-166's Alertmanager until HttpGatewayErrors fires; check the api's probe stays 200/503 without an alert

# --- S.3 [VM vm-095 · bash] the incident (nginx_upstream_failure, DIAGNOSED, root cause argus-lab-slow) ----------------

# --- S.4 [VM vm-166 · bash] SC-08 down; the alert resolves; baseline and nonint-check after on both ----------------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc08 down </dev/null 2>&1 | tail -2; cd ~
