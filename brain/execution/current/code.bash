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

# (no block yet: next is T-0020 step 4, Brain + PR; the leaker's tmpfs fix reaches vm-166 with the next checkout)

# =====================================================================================
# AFTER-MERGE T-0020 — vm-166 back on main (checkout only)                                           [~3 min]
# Why: the T-0020 PR is merged; vm-166 still runs task/T-0020-sc04-pg-connections b1e7176. main now has the same
#      target-side code (db-probe metrics, Prometheus job, the sc04 leaker with its tmpfs), so nothing is rebuilt.
# MUTATES: the git checkout under /opt/argus-v18/app and /opt/argus-v18/DEPLOYED only; no container is restarted.
# NOT vm-095: it runs task/T-0021-tool-isolation; main's api and worker would not start there before PR #36 merges.
# Undo: sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0020-sc04-pg-connections --as <you>
# Lease: whoever runs it (brain.py start); replace <you> with your handle.
# =====================================================================================

# --- M.1 [VM vm-166 · bash] (ssh argus-vm166) -------------------------------------------------------------------------
grep -q "holder=<you> " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as <you> | tail -8
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo docker ps --format '{{.Names}}' | grep -c '^argus-lab-leaker$'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: DEPLOY OK: <main head> (main); its rebuild hints can be ignored (the same code already runs); ref=main;
#           LAB BASELINE OK; 0 (no leaker running); NO INTERFERENCE.
# VERDICT: all as expected -> OK · anything else -> STOP and read the full output.
