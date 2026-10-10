# OP-004 / OP-008 — VM dry runs on vm-095 (2026-10-10, conantkd, session 0583614fc355). Run by the agent over SSH.
# S.1 [vm-095] session marker + read-only state probe.
# MUTATES: /opt/argus-v18/SESSION only. ROLLBACK: none needed (the next session overwrites it).
# EXPECT: deploy.sh status ends with LAB BASELINE OK; nonint-check before -> NO INTERFERENCE; backups listed.
echo 'holder=conantkd session=0583614fc355' | sudo tee /opt/argus-v18/SESSION >/dev/null
cat /opt/argus-v18/SESSION
cat /opt/argus-v18/DEPLOYED 2>/dev/null
sudo bash /opt/argus-v18/app/ops/deploy.sh status | tail -6
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^argus-v18-' | sort
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo ls -la /opt/argus-v18/backups | tail -12
sudo git -C /opt/argus-v18/app log --oneline -1
sudo git -C /opt/argus-v18/app remote -v | head -1
ls /opt/argus-v18/app/Dockerfile* /opt/argus-v18/app/deploy 2>/dev/null | head
docker images --format '{{.Repository}}:{{.Tag}} {{.CreatedSince}}' | grep -E '^argus-v18' | head

# S.2 [vm-095] dry runs from the PR branches, without changing the deployed checkout or the running agent.
# MUTATES: /tmp/argus-dryrun; one .verified marker (OP-008 verify);
#   a throwaway argus-lab-pgrestore (always removed); image argus-v18-maint:op004 (removed at the end).
# ROLLBACK: sudo rm -rf /tmp/argus-dryrun; docker rmi argus-v18-maint:op004; the .verified marker may stay.
# EXPECT: VERIFY OK; PRUNE DRY RUN lines; checkpoint dry-run counts; no row or file deleted; NO INTERFERENCE.
# The branch sources are copied from the laptop (root on the VM has no GitHub access):
#   [laptop] git archive origin/task/<branch> | ssh argus-vm095 'mkdir -p /tmp/argus-dryrun/<dir> && tar -x -C …'
set -e
D=/tmp/argus-dryrun
echo "== OP-008 verify latest"; sudo bash $D/op008/ops/db-backup.sh verify latest --as conantkd | tail -3
echo "== OP-008 prune (default KEEP=7)"; sudo bash $D/op008/ops/db-backup.sh prune --as conantkd
echo "== OP-008 prune (KEEP=2, preview only)"; sudo ARGUS_BACKUP_KEEP=2 bash $D/op008/ops/db-backup.sh prune --as conantkd
sudo ls /opt/argus-v18/backups | wc -l
echo "== OP-004 build"; docker build -q -t argus-v18-maint:op004 $D/op004 | tail -1
echo "== OP-004 dry run (30 days)"; sudo ARGUS_MAINTENANCE_IMAGE=argus-v18-maint:op004 bash $D/op004/ops/checkpoint-retention.sh --dry-run --as conantkd
echo "== OP-004 dry run (1 day, preview only)"; sudo ARGUS_MAINTENANCE_IMAGE=argus-v18-maint:op004 ARGUS_CHECKPOINT_RETENTION_DAYS=1 bash $D/op004/ops/checkpoint-retention.sh --dry-run --as conantkd
docker rmi -f argus-v18-maint:op004 >/dev/null; sudo rm -rf $D
docker ps -a --format '{{.Names}}' | grep -c argus-lab-pgrestore || true
sudo bash /opt/argus-v18/app/ops/deploy.sh status | tail -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1

# S.3 [vm-095] cleanup after S.2 stopped at the OP-004 dry run ("missing credential": the owner secret is uid 70, 0400,
# unreadable by root without CAP_DAC_OVERRIDE). MUTATES: removes the temporary image and /tmp folder only.
docker rmi -f argus-v18-maint:op004 >/dev/null; sudo rm -rf /tmp/argus-dryrun
docker ps -a --format '{{.Names}}' | grep -c argus-lab-pgrestore || true
sudo bash /opt/argus-v18/app/ops/deploy.sh status | tail -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1

# S.4 [vm-095] OP-004 dry run again, with the wrapper running as the secret's owner (sources copied from the laptop
# with git archive into /tmp/argus-dryrun/op004). MUTATES: temporary image + /tmp folder, both removed at the end.
# EXPECT: two dry-run count reports, no row deleted; NO INTERFERENCE.
D=/tmp/argus-dryrun
echo "== OP-004 build"; docker build -q -t argus-v18-maint:op004 $D/op004 | tail -1
echo "== OP-004 dry run (30 days)"; sudo ARGUS_MAINTENANCE_IMAGE=argus-v18-maint:op004 bash $D/op004/ops/checkpoint-retention.sh --dry-run --as conantkd
echo "== OP-004 dry run (1 day, preview only)"; sudo ARGUS_MAINTENANCE_IMAGE=argus-v18-maint:op004 ARGUS_CHECKPOINT_RETENTION_DAYS=1 bash $D/op004/ops/checkpoint-retention.sh --dry-run --as conantkd
docker rmi -f argus-v18-maint:op004 >/dev/null; sudo rm -rf $D
sudo bash /opt/argus-v18/app/ops/deploy.sh status | tail -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
