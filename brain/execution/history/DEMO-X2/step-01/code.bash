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
# STEP DEMO-X2.1 — Confirm both VMs before the second deploy window
# Goal: establish the claimed session and observe the deployed commits, lab baseline,
#       Argus containers, health and protected-object check on both VMs.
# Why: the VM state, not the Brain, decides whether the X-2 deploy can proceed.
# MUTATES: /opt/argus-v18/SESSION marker only. Undo: brain.py release at session end.
# Expected: both markers show conantkd/de222ef12a94; LAB BASELINE OK;
#           NO INTERFERENCE on both VMs; write gate remains closed.
# =====================================================================================

# --- 1.1 [VM vm-095 · bash] (ssh argus-vm095) ---
echo 'holder=conantkd session=de222ef12a94' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/deploy.sh status
sudo docker ps --filter name=argus-v18- --format '{{.Names}} {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh
echo 'DEMO-X2 VM095 PROBE OK'

# --- 1.2 [VM vm-166 · bash] (ssh argus-vm166) ---
echo 'holder=conantkd session=de222ef12a94' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/deploy.sh status
sudo docker ps --filter name=argus-v18- --format '{{.Names}} {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh --host-only
echo 'DEMO-X2 VM166 PROBE OK'

# =====================================================================================
# STEP DEMO-X2.2 — Deploy the closed-gate foundation at main 9798950
# Goal: install the reviewed X-3/X-4 code on both VMs, recreate the vm-095 tunnel
#       agent, worker and scheduler, and rebuild the vm-166 target with its full container_id.
# Why: the first action release needs this foundation before its own separate window.
# MUTATES: a verified vm-095 backup; both /opt/argus-v18/app checkouts; vm-095
#          argus-v18-tunnel, argus-v18-agent, argus-v18-worker and
#          argus-v18-scheduler; vm-166 target services.
# Undo vm-095: deploy.sh 7f137da --as conantkd; rebuild the tunnel, agent,
#               worker and scheduler from
#               that checkout with the same compose command below.
# Undo vm-166: deploy.sh 7f137da --as conantkd; rebuild target services with the
#               same compose command below. The backup is retained. No migration.
# Expected: BACKUP OK and VERIFY OK; DEPLOY OK on both; target services running;
#           WRITE GATE CLOSED on both; NO INTERFERENCE on both.
# If it fails: stop at the failed line, inspect that service's recent Docker logs,
#              then run the stated rollback while both leases remain held.
# =====================================================================================

# --- 2.1 [VM vm-095 · bash] (ssh argus-vm095): before, backup, checkout and core services ---
grep -q '^holder=conantkd session=de222ef12a94$' /opt/argus-v18/SESSION || exit 1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as conantkd
sudo bash /opt/argus-v18/app/ops/db-backup.sh verify latest --as conantkd
sudo bash /opt/argus-v18/app/ops/deploy.sh 9798950bf6b0d7b3c26bd7699b39469d6e7ecdbc --as conantkd
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-tunnel argus-v18-agent argus-v18-worker argus-v18-scheduler
cd ~
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
echo 'DEMO-X2 VM095 DEPLOY OK'

# --- 2.2 [VM vm-166 · bash] (ssh argus-vm166): before, checkout, target ---
grep -q '^holder=conantkd session=de222ef12a94$' /opt/argus-v18/SESSION || exit 1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before
sudo bash /opt/argus-v18/app/ops/deploy.sh 9798950bf6b0d7b3c26bd7699b39469d6e7ecdbc --as conantkd
cd /opt/argus-v18/app/deploy/target
sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml up -d --build
cd ~
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh --host-only
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
echo 'DEMO-X2 VM166 DEPLOY OK'
