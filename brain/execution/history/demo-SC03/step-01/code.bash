# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
#   [VM vm-095 · bash]      ssh argus-vm095   (prompt: ubuntu@vm-appsvnic)
#   [VM vm-166 · bash]      ssh argus-vm166   (prompt: ubuntu@agent-test-vnic)
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated".
# =====================================================================================

# =====================================================================================
# DEMO-SC03 — Class demo: dependency root cause (SC-03) on the LangGraph runner
# MUTATES: stops/starts argus-lab-cache on vm-166 only. Undo: [vm-166] sudo docker start argus-lab-cache
# Expected result of the investigation: root cause vm-166/container:argus-lab-cache (the api is the victim).
# =====================================================================================

# --- 0 [LAPTOP · PowerShell] Lease + session marker on both VMs ------------------------------------------------
cd C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
python brain\tools\brain.py start --task DEMO-SC03
git fetch -q origin "+refs/heads/session:refs/remotes/origin/session"
$L = git show origin/session:session.json | ConvertFrom-Json
foreach ($vm in "argus-vm095", "argus-vm166") { ssh -o BatchMode=yes $vm "echo 'holder=$($L.holder) session=$($L.session_id)' | sudo tee /opt/argus-v18/SESSION" }
if (($L.holder -eq "juanbetancurm") -and (-not $L.released)) { "VERDICT 0 OK" } else { "VERDICT 0 STOP: lease not active" }

# --- 1 [VM vm-166 · bash] (ubuntu@agent-test-vnic) Variables + before-check -------------------------------------
CACHE=argus-lab-cache
API=argus-lab-api
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1

# --- 2 [VM vm-095 · bash] (ubuntu@vm-appsvnic) Variables ---------------------------------------------------------
read -rsp "Shared Argus password: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
ARGUS="sudo --preserve-env=ARGUS_PASSWORD docker exec -it -e ARGUS_USER=juanbetancurm -e ARGUS_PASSWORD argus-v18-agent argus"
API=vm-166/container:argus-lab-api

# =====================================================================================
# DEMO
# =====================================================================================

# --- [vm-166] check
sudo docker ps --filter name=argus-lab --format 'table {{.Names}}\t{{.Status}}'

# --- [vm-095] Argus: status
$ARGUS diagnose $API --check --reason "status"

# --- [vm-166] stop cache
sudo docker stop $CACHE

# --- [vm-166] check (repeat until the api shows "unhealthy", ~1 min; then wait 30 s more)
sudo docker ps --filter name=argus-lab --format 'table {{.Names}}\t{{.Status}}'

# --- [vm-095] Argus: investigation
$ARGUS diagnose $API --reason "api returns errors"

# --- [vm-166] start cache
sudo docker start $CACHE

# --- [vm-166] check (repeat until the api shows "healthy", ~30 s)
sudo docker ps --filter name=argus-lab --format 'table {{.Names}}\t{{.Status}}'

# --- [vm-095] Argus: status
$ARGUS diagnose $API --check --reason "status"

# =====================================================================================
# AFTER THE DEMO
# =====================================================================================

# --- [vm-166] after-check
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1       # expected: NO INTERFERENCE

# --- [vm-095] after-check
unset ARGUS_PASSWORD
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1       # expected: NO INTERFERENCE

# --- [LAPTOP] release the lease (only after the class)
python brain\tools\brain.py release
