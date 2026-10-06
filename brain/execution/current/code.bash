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
# AFTER-MERGE (remaining part) — put vm-166 on `main`                                            [~3 min]
# Why: AFTER-MERGE step 01 (2026-10-06) moved vm-095 to `main` 2097eb1, but its A.1 block (vm-166) was not run.
#   vm-166 still has the checkout 58a51c3; its services are identical to `main`, so nothing is rebuilt.
# MUTATES: the git checkout on vm-166 (+ DEPLOYED marker). Undo: deploy.sh 58a51c3 --as <you>.
# =====================================================================================

# --- B.0 [LAPTOP · PowerShell] Lease + session marker on vm-166 (MUTATES the session branch + SESSION file) -------
python brain\tools\brain.py start --task AFTER-MERGE-166
git fetch -q origin "+refs/heads/session:refs/remotes/origin/session"
$L = git show origin/session:session.json | ConvertFrom-Json
ssh -o BatchMode=yes argus-vm166 "echo 'holder=$($L.holder) session=$($L.session_id)' | sudo tee /opt/argus-v18/SESSION"
if (($L.holder -eq "juanbetancurm") -and (-not $L.released)) { "VERDICT B.0 OK" } else { "VERDICT B.0 STOP: lease not yours/active" }

# --- B.1 [VM vm-166 · bash] (ubuntu@agent-test-vnic — check the prompt!) Move the checkout to main ----------------
ME=juanbetancurm
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "session marker: mine" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as $ME
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: "DEPLOY OK: <main commit> (main) on ...vm166..." (its hint names only the agent of vm-095: nothing to do
# here), ref=main, LAB BASELINE OK, NO INTERFERENCE.

# --- B.2 [LAPTOP · PowerShell] Release the lease ------------------------------------------------------------------
python brain\tools\brain.py release
# >>> Paste everything into output.bash and tell the agent "output.bash updated". <<<
