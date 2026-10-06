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
# AFTER-MERGE — run ONLY after the LAB-BASELINE + LGS pull request is merged into main                  [~5 min]
# Why: both VMs run the checkout of task/lab-baseline-check (58a51c3); only ops/deploy.sh differs from main, so
#   moving to main rebuilds nothing. Needs the VM lease (brain.py start) and the session marker on both VMs.
# MUTATES: the git checkout on both VMs (+ DEPLOYED marker). Undo: deploy.sh task/lab-baseline-check --as <you>.
# =====================================================================================

# --- M.1 [VM vm-166 · bash] then the same on [VM vm-095 · bash] -------------------------------------------------
ME=<your-github-handle>
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "session marker: mine" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as $ME | tail -4
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: "DEPLOY OK: <main commit> (main)" with no rebuild hints, ref=main, LAB BASELINE OK, NO INTERFERENCE.
