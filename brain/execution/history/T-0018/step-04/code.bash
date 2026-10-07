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
# T-0018 step 04 — deploy the SC-07 code on both VMs (no scenario yet)                              [~10 min]
# Why: vm-166 runs the target services that now return `networks` and probe a dependency only while its owner runs;
#      vm-095 runs the agent, which reads config/ (the new SC-07 targets) from its checkout and shows `networks` to the
#      model (code baked in the image). Step 01 proved 172.30.3.0/24 is free on vm-166 (SUBNET FREE).
#      Note: the vm-095 agent image then also carries T-0015 (already on main); T-0015 step 6 can still prove the
#      read-token refusal on top of it.
# MUTATES: the checkout on both VMs; rebuilds the 4 target services on vm-166 (read-gateway, host-probe,
#          network-probe, exporter: a few seconds each) and argus-v18-agent on vm-095. No lab container changes.
# Undo: on each VM `sudo bash /opt/argus-v18/app/ops/deploy.sh main --as conantkd`, then the same rebuild command.
# Lease: conantkd (session 796fd4f3bf61); both SESSION markers already say so.
# =====================================================================================

# --- T.1 [VM vm-166 · bash] (ssh argus-vm166) checkout + rebuild the target services (MUTATES) ----------------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0018-sc07-network --as $ME | tail -8
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml up -d --build 2>&1 | tail -6; cd ~
sleep 15
sudo docker ps --format '{{.Names}}\t{{.Status}}' | grep -E '^argus-(v18|lab)-' | sort
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; "DEPLOY OK: <branch head> (task/T-0018-sc07-network)"; the 4 target services rebuilt and Up
#           (seconds), argus-lab-api / -cache untouched; ref=task/T-0018-sc07-network; LAB BASELINE OK; NO INTERFERENCE.

# --- T.2 [VM vm-095 · bash] (ssh argus-vm095) checkout + rebuild the agent + H-1 on vm-166 (MUTATES; no model call) --
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0018-sc07-network --as $ME | tail -8
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent 2>&1 | tail -4; cd ~
for i in $(seq 1 12); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz); echo "health $c"; [ "$c" = 200 ] && break; sleep 5; done
read -rsp "Argus password for $ME: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
ARGUS="sudo --preserve-env=ARGUS_PASSWORD docker exec -i -e ARGUS_USER=$ME -e ARGUS_PASSWORD argus-v18-agent argus"
$ARGUS diagnose vm-166/container:argus-lab-api --check --reason "T-0018 H-1 after the deploy" --no-color < /dev/null | grep -E '^incident|outcome'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
echo "T-0018.4 DEPLOY DONE"
# Expected: SESSION OK; "DEPLOY OK: <branch head> (task/T-0018-sc07-network)"; argus-v18-agent recreated; health 200;
#           the H-1 check on vm-166's api says outcome HEALTHY (no model call); NO INTERFERENCE; T-0018.4 DEPLOY DONE.
