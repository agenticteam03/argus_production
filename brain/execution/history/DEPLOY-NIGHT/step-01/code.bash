# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# DEPLOY-NIGHT (2026-10-21) — vm-095 to main 024aa6f: migration 009 (link_event, #220), T-0046 L1 (#219), #221
#   (one link per dependency; host.read_file no longer raises), the ACR-0027/0028 texts; and the OP-004 / OP-008 dry
#   runs. vm-166 does not change (L1 renders the same target config).                                   [~20 min]
# MUTATES: vm-095 (backup, checkout, migration 009, agent image). Both leases. The dry runs only read.
# ROLLBACK: deploy.sh b2e3548 --as conantkd, then the compose command of D.1. Migration 009 stays (the old image does
#   not read link_event).
# Note: no manual `argus deploy record`: deploy.sh records the event itself (DEPLOY-215 recorded it twice).
# =====================================================================================

# --- D.0 [LAPTOP · PowerShell] both leases, then each VM's session marker --------------------------------------------
python brain/tools/brain.py --as conantkd start --task DEPLOY-NIGHT --vm both
#   [VM vm-095 · bash] and [VM vm-166 · bash]  echo 'holder=conantkd session=<id>' | sudo tee /opt/argus-v18/SESSION >/dev/null

# --- D.0b [VM vm-166 · bash] before (read-only) -----------------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1

# --- D.1 [VM vm-095 · bash] probe, backup, deploy, migrate 009, rebuild (MUTATES) -------------------------------------
ME=conantkd; BR=024aa6f
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
free -m | awk '/Mem/{print "mem available " $7 " MiB"}'
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -3
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "\+ |REFUSED|schema:"
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
cd ~
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"

# --- D.2 [VM vm-095 · bash] verification (read-only) ------------------------------------------------------------------
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f "{{.Image}}" $c </dev/null | cut -c8-19) $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
sudo docker logs --tail 8 argus-v18-agent 2>&1 </dev/null | grep -i -E "startup validation|threshold|error" || echo "agent: no startup errors"
sudo docker logs --tail 8 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
sudo docker exec argus-v18-agent argus db check </dev/null | grep -E "FAIL|checks passed"
for p in /api/v1/topology /api/v1/overview /api/v1/me /docs; do echo "GET $p $(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1$p </dev/null)"; done
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1

# --- D.3 [VM vm-166 · bash] after (read-only) -------------------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1

# --- D.4 [VM vm-095 · bash] OP-004 and OP-008 dry runs (read-only: nothing is deleted) --------------------------------
sudo bash /opt/argus-v18/app/ops/checkpoint-retention.sh --dry-run --as conantkd </dev/null 2>&1 | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh prune --as conantkd </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1

# --- D.5 [LAPTOP · PowerShell] release the leases ---------------------------------------------------------------------
python brain/tools/brain.py --as conantkd release
