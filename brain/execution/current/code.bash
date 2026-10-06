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
# STEP T-0017.3 — Postgres backup/restore drill on vm-095                          [~5 min]
# Goal / Why: take a real backup of the Argus database and prove it restores (phase 5, last missing item).
# MUTATES: checks out task/T-0017-pg-backup-drill in /opt/argus-v18/app (only ops/, tests/ and brain/ differ: no
#          rebuild); creates /opt/argus-v18/backups/ (one dump, root-only); starts and removes argus-lab-pgrestore.
#          The live database argus-v18-postgres is only READ.
# Undo:    sudo bash /opt/argus-v18/app/ops/deploy.sh main --as conantkd   (after the PR merges this is the normal
#          AFTER-MERGE step);  sudo rm -rf /opt/argus-v18/backups   (only if you want to drop the dump)
# =====================================================================================

# --- 3.1 [VM vm-095 · bash] (ssh argus-vm095) Session marker and "before" snapshot ---------------------------
grep -q "holder=conantkd " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION"
# Expected: SESSION OK
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before
# Expected: saved /opt/argus-v18/baseline/before.txt (...)

# --- 3.2 [VM vm-095 · bash] Check out the task branch (no restart, no rebuild) -------------------------------
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0017-pg-backup-drill --as conantkd
# Expected: DEPLOY OK: 23afbeb... (task/T-0017-pg-backup-drill) and NO service to rebuild

# --- 3.3 [VM vm-095 · bash] Backup (reads the live database only) ------------------------------------------
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as conantkd
# Expected: "  11 tables, <about 4600> rows" and "BACKUP OK: /opt/argus-v18/backups/argus-<UTC>.dump (<bytes>)"
# If "BACKUP STOP: the database changed during the dump": an investigation was writing; just run 3.3 again.
sudo ls -la /opt/argus-v18/backups
# Expected: drwx------ root; three files -rw------- root: .dump, .dump.sha256, .fingerprint

# --- 3.4 [VM vm-095 · bash] Verify: restore into a throwaway container and compare -------------------------
DUMP=$(sudo ls -1t /opt/argus-v18/backups/argus-*.dump | head -1); echo "$DUMP"
sudo bash /opt/argus-v18/app/ops/db-backup.sh verify "$DUMP" --as conantkd
# Expected: VERIFY OK: 11 tables, <same rows as 3.3> rows match   (~20 s: the container starts, restores, compares)

# --- 3.5 [VM vm-095 · bash] Nothing left behind; the live database untouched -------------------------------
sudo docker ps -a --format '{{.Names}}' | grep -x argus-lab-pgrestore || echo "restore container removed"
# Expected: restore container removed
sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E '^argus-v18-(postgres|agent) '
# Expected: argus-v18-postgres Up ... (healthy) — same uptime as before (never restarted); argus-v18-agent Up ...
sudo bash /opt/argus-v18/app/ops/deploy.sh status
# Expected: ref=task/T-0017-pg-backup-drill, LAB BASELINE OK

# --- 3.6 [VM vm-095 · bash] Prove non-interference ---------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: NO INTERFERENCE
echo "T-0017.3 DRILL DONE"
# >>> Paste everything into output.bash and tell the agent "output.bash updated". <<<
