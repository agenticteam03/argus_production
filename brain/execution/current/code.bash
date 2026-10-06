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
# AFTER-MERGE — put both VMs back on `main` after PRs #15, #16, #17 and #8                        [~10 min]
# Why: both VMs run the checkout of task/lab-baseline-check (58a51c3). Since then `main` changed only documentation
#   and argus/orchestration/graph_runner.py (PR #16: named constants, identical behaviour). vm-166 only moves its
#   checkout; vm-095 also rebuilds the agent, so the running image matches the deployed commit.
# MUTATES: the git checkout on both VMs (+ DEPLOYED marker); rebuilds argus-v18-agent on vm-095.
# Undo: sudo bash /opt/argus-v18/app/ops/deploy.sh 58a51c3 --as juanbetancurm  (on vm-095: then rebuild as in A.2).
# =====================================================================================

# --- A.0 [LAPTOP · PowerShell] Lease + session marker on both VMs (MUTATES the session branch + SESSION files) -----
cd C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git switch main
python brain\tools\brain.py start --task AFTER-MERGE
git fetch -q origin "+refs/heads/session:refs/remotes/origin/session"
$L = git show origin/session:session.json | ConvertFrom-Json
foreach ($vm in "argus-vm095", "argus-vm166") { ssh -o BatchMode=yes $vm "echo 'holder=$($L.holder) session=$($L.session_id)' | sudo tee /opt/argus-v18/SESSION" }
if (($L.holder -eq "juanbetancurm") -and (-not $L.released)) { "VERDICT A.0 OK" } else { "VERDICT A.0 STOP: lease not yours/active" }
# Expected: "Lease CLAIMED by juanbetancurm until ...", both VMs print the same holder/session line, "VERDICT A.0 OK".

# --- A.1 [VM vm-166 · bash] (ubuntu@agent-test-vnic) Move the checkout to main (MUTATES files only) ---------------
ME=juanbetancurm
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "session marker: mine" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as $ME
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: "DEPLOY OK: <main commit> (main)". Its rebuild hint names only the agent (vm-095): nothing to do on
# vm-166. Then ref=main, LAB BASELINE OK, NO INTERFERENCE.

# --- A.2 [VM vm-095 · bash] (ubuntu@vm-appsvnic) Deploy main + rebuild the agent (MUTATES: argus-v18-agent) -------
ME=juanbetancurm
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "session marker: mine" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as $ME
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml \
  up -d --build --no-deps argus-v18-agent < /dev/null; cd ~
sleep 15
RUNNER=$(sudo docker exec argus-v18-agent python -c "from argus.infrastructure.wiring import Settings; print(Settings().runner)")
echo "agent runner: $RUNNER"
curl -s http://127.0.0.1:18000/healthz; echo
sudo docker exec argus-v18-agent argus db check | grep -q '^15/15 database checks passed' && [ "$RUNNER" = langgraph ] \
  && echo "VERDICT A.2 OK: vm-095 on main, agent rebuilt on LangGraph, db check 15/15" || echo "VERDICT A.2 STOP"
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: "DEPLOY OK: <main commit> (main)" with the agent hint (no migration hint), "agent runner: langgraph",
# healthz "ok":true, "VERDICT A.2 OK", ref=main, LAB BASELINE OK, NO INTERFERENCE.

# --- A.3 [LAPTOP · PowerShell] Release the lease ----------------------------------------------------------------
python brain\tools\brain.py release
# >>> Paste everything into output.bash and tell the agent "output.bash updated". <<<
