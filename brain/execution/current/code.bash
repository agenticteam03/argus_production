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
# OP-011 step 03 — ACR-0004 on the VMs: SC-03 must give ONE incident (2026-10-09, conantkd, session 75c48aa9bfad).
# WHY: step 02 showed the second SC-03 alert arriving after the first incident closed; ACR-0004 attaches an alert that
#   started before that incident closed. Done when SC-03 opens one incident with occurrences [started, attached].
# MUTATES: vm-095: the agent image (agent, worker, scheduler recreated; no migration). vm-166: checkout only. Lab:
#   cache stopped then started; incident rows.
# ROLLBACK: deploy.sh ca7977c (step 02) on both VMs + rebuild agent/worker/scheduler on vm-095.
# NOTE: `docker compose` reads stdin: every command in a `bash -s` script gets </dev/null.
# =====================================================================================

# --- S.1 [VM vm-095 · bash] deploy and rebuild ---------------------------------------------------------------------------
ME=conantkd
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/OP-011-correlation --as $ME </dev/null | tail -1   # DEPLOY OK
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | tail -1                                 # schema unchanged (004)
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E 'Started|Error' | tail -4; cd ~

# --- S.2 [VM vm-166 · bash] same ref, then SC-03 -------------------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/deploy.sh task/OP-011-correlation --as conantkd </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo docker stop argus-lab-cache </dev/null
# poll the vm-166 Alertmanager until DependencyProbeFailed AND ContainerUnhealthy fire (every 10 s, max 5 min)

# --- S.3 [VM vm-095 · bash] one incident ---------------------------------------------------------------------------------
# /tmp/op011_probe.py inside argus-v18-worker (as in step 02) until the incidents since the stop are concluded and
#   two passes have run after both alerts fired. Expected: ONE incident, occurrences [started, attached],
#   evidence version 2; scheduler: started 1, then attached 1 (same pass or the next), then duplicate 2.

# --- S.4 [VM vm-166 · bash] reset ----------------------------------------------------------------------------------------
sudo docker start argus-lab-cache </dev/null
# poll until no alert is active; then LAB BASELINE and nonint-check after on both VMs
