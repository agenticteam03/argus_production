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
# AFTER-MERGE (T-0017) — put vm-095 back on `main` (f126272) after PR #25                          [~3 min]
# Why: vm-095 runs the checkout of task/T-0017-pg-backup-drill. main (f126272) has T-0017 plus T-0015 (read-only
#      tokens, /me: argus/adapters/inbound/http.py) and T-0016 (frontend/). This block moves the checkout only.
#      deploy.sh will hint an agent rebuild: do NOT run it here; that rebuild is T-0015 step 6 (juanbetancurm).
# MUTATES: /opt/argus-v18/SESSION (M.0) and the checkout in /opt/argus-v18/app + DEPLOYED marker (M.2).
# Undo: sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0017-pg-backup-drill --as conantkd
# Lease: claimed by conantkd (session 796fd4f3bf61); vm-166 is already on main and is not touched.
# =====================================================================================

# --- M.0 [LAPTOP · PowerShell] Session marker on vm-095 (MUTATES /opt/argus-v18/SESSION) ---------------------------
ssh -o BatchMode=yes argus-vm095 "echo 'holder=conantkd session=796fd4f3bf61' | sudo tee /opt/argus-v18/SESSION"
# Expected: holder=conantkd session=796fd4f3bf61

# --- M.1 [VM vm-095 · bash] (ssh argus-vm095) State probe — read-only ---------------------------------------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - stop here"
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo docker ps --format '{{.Names}}\t{{.Status}}' | grep -E '^argus-v18-' | sort
curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:18000/healthz
sudo ls -l /opt/argus-v18/backups/
# Expected: SESSION OK; commit=aba61c1… ref=task/T-0017-pg-backup-drill; LAB BASELINE OK;
#           argus-v18-* Up (postgres healthy); health 200; one root-only argus-20261006T185011Z.dump (+ .sha256, .fingerprint)

# --- M.2 [VM vm-095 · bash] Move the checkout to main (MUTATES files only, no restart) -----------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh main --as $ME
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo docker ps --format '{{.Names}}\t{{.Status}}' | grep -E '^argus-v18-(agent|postgres)'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
echo "AFTER-MERGE T-0017 DONE"
# Expected: "DEPLOY OK: f126272… (main)"; the rebuild hint names the agent (leave it for T-0015 step 6);
#           commit=f126272… ref=main; LAB BASELINE OK; agent and postgres keep the same uptime as in M.1 (no restart);
#           NO INTERFERENCE; AFTER-MERGE T-0017 DONE
