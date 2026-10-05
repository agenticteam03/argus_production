# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
#   [VM vm-095 · bash]      ssh argus-vm095
#   [VM vm-166 · bash]      ssh argus-vm166
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated". Every block ends with a VERDICT line.
# (Task B6d is done; its commands are in the history of this file on main.)
# =====================================================================================

# =====================================================================================
# T-0013 STEP 5 — The agent on LangGraph with Postgres checkpoints, on the real VMs   [~40 min]
# Why: verify on vm-095 what the tests proved on the laptop: same diagnoses, and every run checkpointed in Postgres.
# What changes:
#   - both VMs: /opt/argus-v18/app becomes a git checkout (deploy.sh init; the old folder is kept as app.pre-git-<time>)
#   - vm-095: migration 002 (checkpoint tables), the agent image rebuilt and restarted with ARGUS_RUNNER=langgraph
#     (this redeploy also ships the runbooks inside the image, D-002)
#   - lab: SC-01 worker started on vm-166, then removed
# Rollback (vm-095): cd /opt/argus-v18/app/deploy/vm-095 && sudo ARGUS_RUNNER=plain docker compose --env-file
#   /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent   (the 002 tables stay, unused)
# =====================================================================================

# --- S5.1 [LAPTOP · PowerShell] Push the branch, claim the VM session, write the marker on both VMs -----------------
cd C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git push origin task/T-0013-langgraph-skeleton
python brain\tools\brain.py start --task T-0013
git fetch -q origin "+refs/heads/session:refs/remotes/origin/session"
$L = git show origin/session:session.json | ConvertFrom-Json
$ok = 0
foreach ($vm in "argus-vm095", "argus-vm166") {
  $got = ssh -o BatchMode=yes $vm "echo 'holder=$($L.holder) session=$($L.session_id)' | sudo tee /opt/argus-v18/SESSION >/dev/null; cat /opt/argus-v18/SESSION"
  "${vm}: $got"
  if ("$got" -eq "holder=$($L.holder) session=$($L.session_id)") { $ok++ }
}
$unpushed = git rev-list --count origin/task/T-0013-langgraph-skeleton..task/T-0013-langgraph-skeleton
if (($ok -eq 2) -and ($L.holder -eq "juanbetancurm") -and (-not $L.released) -and ($unpushed -eq "0")) { "VERDICT S5.1 OK: branch pushed, lease yours, marker on both VMs" } else { "VERDICT S5.1 STOP: unpushed=$unpushed holder=$($L.holder) released=$($L.released) markers=$ok" }

# --- S5.2 [VM vm-166 · bash] (ssh argus-vm166) Baseline, then turn app/ into a git checkout of main (files only) ---
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before
D=/opt/argus-v18/secrets/deploy
sudo rm -rf /tmp/argus-bootstrap
sudo GIT_SSH_COMMAND="ssh -i $D/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=$D/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes" \
  git clone -q --depth 1 git@github.com:agenticteam03/argus_production.git /tmp/argus-bootstrap
sudo bash /tmp/argus-bootstrap/ops/deploy.sh init main --as juanbetancurm
sudo rm -rf /tmp/argus-bootstrap
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|checkout:'
sudo docker ps --filter name=argus- --format '{{.Names}} {{.Status}}'
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -q 'local modifications: 0' \
  && echo "VERDICT S5.2 OK: vm-166 app/ is a clean checkout of main" || echo "VERDICT S5.2 STOP"
# Expected: "saved .../before.txt", "DEPLOY OK: <commit> (main) on agent-test-vnic", every argus-* container still Up.
# (Ignore the "rebuild" hints printed by deploy.sh: nothing on vm-166 is rebuilt in this task.)

# --- S5.3 [VM vm-095 · bash] (ssh argus-vm095) Baseline, then app/ = the T-0013 branch (files only) -----------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before
D=/opt/argus-v18/secrets/deploy
sudo rm -rf /tmp/argus-bootstrap
sudo GIT_SSH_COMMAND="ssh -i $D/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=$D/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes" \
  git clone -q --depth 1 git@github.com:agenticteam03/argus_production.git /tmp/argus-bootstrap
sudo bash /tmp/argus-bootstrap/ops/deploy.sh init task/T-0013-langgraph-skeleton --as juanbetancurm
sudo rm -rf /tmp/argus-bootstrap
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|checkout:'
test -f /opt/argus-v18/app/deploy/migrations/002_checkpoints.sql \
  && echo "VERDICT S5.3 OK: vm-095 app/ is the T-0013 branch" || echo "VERDICT S5.3 STOP: 002 migration missing"
# Expected: "DEPLOY OK: <commit> (task/T-0013-langgraph-skeleton) on vm-appsvnic", "local modifications: 0".

# --- S5.4 [VM vm-095 · bash] Migration 002, then rebuild the agent on LangGraph (MUTATES Postgres + the agent) -------
cd /opt/argus-v18/app && sudo bash ops/db-migrate.sh
cd /opt/argus-v18/app/deploy/vm-095 && sudo ARGUS_RUNNER=langgraph docker compose --env-file /opt/argus-v18/hosts.env \
  -f compose.core.yml up -d --build --no-deps argus-v18-agent && cd ~
sleep 15
RUNNER=$(sudo docker exec argus-v18-agent python -c "from argus.infrastructure.wiring import Settings; print(Settings().runner)")
echo "agent runner: $RUNNER"
sudo docker exec argus-v18-agent argus db check | tail -4
sudo docker exec argus-v18-agent argus db check | grep -q '^15/15 database checks passed' && [ "$RUNNER" = langgraph ] \
  && echo "VERDICT S5.4 OK: 002 applied, agent on LangGraph, db check 15/15" || echo "VERDICT S5.4 STOP"
# Expected: "+ 002_checkpoints applied" (or "= ... already applied"), "Container argus-v18-agent Started" (the build
# takes a few minutes the first time: it downloads LangGraph), "agent runner: langgraph", "15/15 database checks passed".

# --- S5.5 [VM vm-095 · bash] H-1 (healthy, no model) and SC-09 (unsupported, evidence pack) ---------------------------
read -rsp "Shared Argus password: " ARGUS_PASSWORD; echo; export ARGUS_PASSWORD
argus() { sudo --preserve-env=ARGUS_PASSWORD docker exec -i -e ARGUS_USER=juanbetancurm -e ARGUS_PASSWORD argus-v18-agent argus "$@"; }
ckpt() { sudo docker exec argus-v18-postgres psql -U argus_owner -d argus -At -c "SELECT count(DISTINCT thread_id) FROM checkpoints"; }
BEFORE=$(ckpt)
H1=$(argus diagnose vm-166/container:argus-lab-api --check --reason "T-0013 H-1" | grep -E '^incident|outcome'); echo "$H1"
S9=$(argus diagnose vm-095/container:argus-lab-api --reason "users see stale data" | grep -E '^incident|outcome'); echo "$S9"
AFTER=$(ckpt); echo "checkpointed investigations: $BEFORE -> $AFTER"
echo "$H1" | grep -q 'HEALTHY' && echo "$S9" | grep -qi 'unsupported' && [ "$AFTER" -ge $((BEFORE + 2)) ] \
  && echo "VERDICT S5.5 OK: same outcomes as before, both runs checkpointed in Postgres" || echo "VERDICT S5.5 STOP"

# --- S5.6 [VM vm-166 · bash] Start SC-01 (OOM restart loop) and wait for 3+ restarts (MUTATES: lab worker) ------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 up -d argus-lab-worker-oom && cd ~
for i in $(seq 1 18); do r=$(sudo docker inspect -f '{{.RestartCount}}' argus-lab-worker 2>/dev/null || echo 0); echo "restarts=$r"; [ "$r" -ge 3 ] && break; sleep 10; done
[ "$r" -ge 3 ] && echo "VERDICT S5.6 OK: SC-01 worker is crash-looping" || echo "VERDICT S5.6 STOP: fewer than 3 restarts"

# --- S5.7 [VM vm-095 · bash] SC-01: Argus diagnoses it on LangGraph ---------------------------------------------------
BEFORE=$(ckpt)
argus diagnose vm-166/container:argus-lab-worker --reason "keeps restarting" | tee /tmp/sc01.txt | tail -25
AFTER=$(ckpt); echo "checkpointed investigations: $BEFORE -> $AFTER"
grep -qi 'outcome.*diagnosed' /tmp/sc01.txt && grep -q 'RB-001' /tmp/sc01.txt && [ "$AFTER" -gt "$BEFORE" ] \
  && echo "VERDICT S5.7 OK: SC-01 diagnosed (RB-001) on LangGraph, checkpointed in Postgres" || echo "VERDICT S5.7 STOP"
rm -f /tmp/sc01.txt; unset ARGUS_PASSWORD
# Expected: DETECT container_restart_loop -> RECALL RB-001 -> INVESTIGATE/ACT on vm-166 only -> RECORD: diagnosed (OOM).

# --- S5.8 [VM vm-166 · bash] Reset SC-01, prove non-interference -------------------------------------------------
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom && cd ~
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: NO INTERFERENCE: non-Argus objects unchanged

# --- S5.9 [VM vm-095 · bash] Prove non-interference ----------------------------------------------------------------
sudo docker ps --filter name=argus- --format '{{.Names}} {{.Status}}'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: every argus-* container Up (argus-v18-agent recently restarted), NO INTERFERENCE

# --- S5.10 [LAPTOP · PowerShell] Release the VM session ------------------------------------------------------------
cd C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
python brain\tools\brain.py release
# Expected: "Lease released."
