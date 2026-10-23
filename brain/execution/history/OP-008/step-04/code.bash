# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# OP-008 step 04 (2026-10-21) — vm-095: verify the newest backup, preview the prune, the sha256 after-check left
#   open by step 03. Read-only for the live database (verify restores into a throwaway container).     [~15 min]
# MUTATES: vm-095: one `.verified` marker and a throwaway restore container (removed by the script). Lease vm-095.
# The `prune --apply` is NOT run here: it waits for a teammate's approval (as PR #138 for step 03).
# =====================================================================================

# --- S.0 [LAPTOP · PowerShell] lease; marker -------------------------------------------------------------------------
python brain/tools/brain.py --as conantkd start --task OP-008-prune --vm vm-095
#   [VM vm-095 · bash]  echo 'holder=conantkd session=<id>' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
df -h /opt/argus-v18 | tail -1; sudo du -sh /opt/argus-v18/backups

# --- S.1 [VM vm-095 · bash, conantkd's terminal] the dry run (the agent's permission check refused it) ----------------
sudo bash /opt/argus-v18/app/ops/db-backup.sh prune --as conantkd </dev/null

# --- S.2 [VM vm-095 · bash] verify the newest backup, then the checksums of both verified ones -----------------------
sudo bash /opt/argus-v18/app/ops/db-backup.sh verify /opt/argus-v18/backups/argus-20261021T201818Z.dump --as conantkd </dev/null | tail -2
sudo bash -c 'cd /opt/argus-v18/backups && for b in argus-20261014T162458Z argus-20261021T201818Z; do sha256sum -c $b.dump.sha256; test -f $b.verified && echo $b.verified present; done; ls | grep -c "\.dump$"'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1

# --- S.3 [LAPTOP · PowerShell] release -------------------------------------------------------------------------------
python brain/tools/brain.py --as conantkd release

# --- Later, after approval: [VM vm-095 · bash] the apply (KEEP=7), then the after-checks of step 03 ------------------
#   sudo bash /opt/argus-v18/app/ops/db-backup.sh prune --as conantkd --apply </dev/null
