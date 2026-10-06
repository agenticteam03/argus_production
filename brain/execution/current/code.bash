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
# STEP T-0017.3b — Verify the backup (re-run of 3.4 with `verify latest`)          [~2 min]
# Goal / Why: 3.3 made the backup; 3.4 could not find it (the shell expanded the glob before sudo in a root-only
#             folder). The script now finds the newest dump itself.
# MUTATES: updates the checkout to the branch head (only ops/ and tests/ differ: no rebuild); starts and removes
#          argus-lab-pgrestore. The live database is not touched.
# Undo:    sudo bash /opt/argus-v18/app/ops/deploy.sh main --as conantkd   (the normal AFTER-MERGE step)
# =====================================================================================

# --- 3b.1 [VM vm-095 · bash] (ssh argus-vm095) Session marker and "before" snapshot --------------------------
grep -q "holder=conantkd " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION"
# Expected: SESSION OK
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before
# Expected: saved /opt/argus-v18/baseline/before.txt (...)

# --- 3b.2 [VM vm-095 · bash] Update the checkout to the branch head ----------------------------------------
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0017-pg-backup-drill --as conantkd
# Expected: DEPLOY OK: <the branch head> (task/T-0017-pg-backup-drill) and NO service to rebuild

# --- 3b.3 [VM vm-095 · bash] Verify the newest dump --------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/db-backup.sh verify latest --as conantkd
# Expected: "  dump: /opt/argus-v18/backups/argus-20261006T185011Z.dump"
#           "VERIFY OK: 11 tables, 4603 rows match"   (~20 s)

# --- 3b.4 [VM vm-095 · bash] Nothing left behind; the live database untouched ------------------------------
sudo docker ps -a --format '{{.Names}}' | grep -x argus-lab-pgrestore || echo "restore container removed"
# Expected: restore container removed
sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E '^argus-v18-(postgres|agent) '
# Expected: argus-v18-postgres Up ~15 hours (healthy) — never restarted; argus-v18-agent Up ...
sudo bash /opt/argus-v18/app/ops/deploy.sh status
# Expected: ref=task/T-0017-pg-backup-drill, LAB BASELINE OK

# --- 3b.5 [VM vm-095 · bash] Prove non-interference --------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after
# Expected: NO INTERFERENCE
echo "T-0017.3b VERIFY DONE"
# >>> Paste everything into output.bash and tell the agent "output.bash updated". <<<
