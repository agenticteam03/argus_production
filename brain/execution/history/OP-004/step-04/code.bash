# OP-004 / OP-008 — the approved applies on vm-095 (2026-10-14, conantkd). Run by conantkd on the VM.
# Approval: juanbetancurm in PR #138 (one OP-008 `prune --apply` with KEEP=7; one OP-004 `--apply` at 30 days;
# the daily timer stays off). Scripts from the deployed `main` checkout.
# Lease: NOT claimed in the Brain for this run (released at 06:59Z after AFTER-MERGE-main); the VM marker still named
# conantkd from that session, so the scripts' marker check passed. See the journal entry of 2026-10-14.

# S.1 [vm-095] state and a fresh, verified backup.
# MUTATES: one new backup set and its .verified marker; a throwaway argus-lab-pgrestore (always removed).
# ROLLBACK: none needed (a backup set is additive).
# EXPECT: LAB BASELINE OK; BACKUP OK; VERIFY OK.
cat /opt/argus-v18/SESSION
sudo bash /opt/argus-v18/app/ops/deploy.sh status | tail -2
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as conantkd | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh verify latest --as conantkd | tail -1

# S.2 [vm-095] OP-008: preview, then the approved apply (KEEP=7, the newest verified set always kept).
# MUTATES: deletes the backup sets older than the 7 newest. ROLLBACK: none (deletion); the kept sets include the
# newest verified one, restored in S.1.
# EXPECT: the dry-run list equals the apply list; 7 sets remain.
sudo bash /opt/argus-v18/app/ops/db-backup.sh prune --as conantkd
sudo bash /opt/argus-v18/app/ops/db-backup.sh prune --as conantkd --apply
sudo ls -la /opt/argus-v18/backups | tail -25

# S.3 [vm-095] OP-004: preview, then the approved apply (30 days).
# MUTATES: deletes checkpoint rows of incidents final for more than 30 days (none expected today); one audit record
# `maintenance.checkpoints_pruned`. ROLLBACK: restore from the S.1 backup.
# EXPECT: DRY RUN and PRUNED counts equal.
sudo bash /opt/argus-v18/app/ops/checkpoint-retention.sh --dry-run --as conantkd
sudo bash /opt/argus-v18/app/ops/checkpoint-retention.sh --apply --as conantkd

# S.4 [vm-095] close.
# MUTATES: nothing. EXPECT: NO INTERFERENCE.
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
