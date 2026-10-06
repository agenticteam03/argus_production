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
# AFTER-MERGE (T-0017) — put vm-095 back on `main` once the T-0017 pull request is merged          [~2 min]
# Why: vm-095 runs the checkout of task/T-0017-pg-backup-drill; it differs from main only in ops/db-backup.sh, tests
#      and the Brain, so nothing is rebuilt. vm-166 is already on main.
# MUTATES: the checkout in /opt/argus-v18/app only.   Undo: deploy.sh task/T-0017-pg-backup-drill --as <you>
# Run it only AFTER the merge, inside your own VM lease (brain.py start; session marker = you).
# =====================================================================================

# --- M.1 [VM vm-095 · bash] (ssh argus-vm095) -------------------------------------------------------------
grep -q "holder=<you> " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as <you>
# Expected: DEPLOY OK: <main head> (main) and NO service to rebuild
sudo bash /opt/argus-v18/app/ops/deploy.sh status
# Expected: ref=main, LAB BASELINE OK
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: NO INTERFERENCE
