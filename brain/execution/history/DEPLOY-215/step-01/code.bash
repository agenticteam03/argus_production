# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# DEPLOY-215 (2026-10-20) — vm-095 to main b2e3548: #203 (a failed baseline read is not kept) and #208's ops scripts
#   (db-backup.sh `1>&"$fd"`, shellcheck annotations). Everything else since 999b5bb is CI, Brain or tests.   [~20 min]
# What changes:
#   vm-095: the checkout, then the agent image (agent, worker, scheduler: incident_metrics.py); no migration (008 stays
#     the newest); a second backup with the new db-backup.sh proves its changed line.
#   vm-166: no change (its lease is held because the agent changes; nonint-check before and after).
# MUTATES: vm-095. Both leases.
# ROLLBACK: deploy.sh 999b5bb --as conantkd, then the compose command of D.1.
# =====================================================================================

# --- D.0 [LAPTOP · PowerShell] both leases, then each VM's session marker --------------------------------------------
python brain/tools/brain.py --as conantkd start --task DEPLOY-215 --vm both
#   [VM vm-095 · bash] and [VM vm-166 · bash]  echo 'holder=conantkd session=<id>' | sudo tee /opt/argus-v18/SESSION >/dev/null

# --- D.0b [VM vm-166 · bash] before (read-only) -----------------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
# Expected: ref=bdcd048, LAB BASELINE OK; the before-state saved.

# --- D.1 [VM vm-095 · bash] state probe, backup, deploy, rebuild (MUTATES) --------------------------------------------
ME=conantkd; BR=b2e3548
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
free -m | awk '/Mem/{print "mem available " $7 " MiB"}'
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -3
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "applied|REFUSED|schema:"
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
cd ~
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
SHA=$(sudo sed -n 's/^commit=//p' /opt/argus-v18/DEPLOYED)
sudo docker exec argus-v18-agent argus deploy record --commit "$SHA" --ref main --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
# Expected: SESSION OK; ref=999b5bb, LAB BASELINE OK; NO INTERFERENCE; BACKUP OK; DEPLOY OK: b2e3548; no migration
#   applied, schema 001 to 008; three "Recreated"; health 200; the deploy event recorded; BACKUP OK again (the new
#   db-backup.sh).

# --- D.2 [VM vm-095 · bash] verification (read-only) ------------------------------------------------------------------
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f "{{.Image}}" $c </dev/null | cut -c8-19) $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
sudo docker logs --tail 8 argus-v18-agent 2>&1 </dev/null | grep -i -E "startup validation|threshold|error" || echo "agent: no startup errors"
sudo docker logs --tail 8 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
for p in /api/v1/topology /api/v1/overview /api/v1/me /docs; do echo "GET $p $(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1$p </dev/null)"; done
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: the three on ONE image, restarts=0; no startup errors; 26/26 database checks; /api/v1 routes 401, /docs
#   404; 55/55; WRITE GATE CLOSED; commit=b2e3548 LAB BASELINE OK; NO INTERFERENCE.

# --- D.3 [VM vm-166 · bash] after (read-only) -------------------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: ref=bdcd048 unchanged, LAB BASELINE OK; NO INTERFERENCE.

# --- D.4 [LAPTOP · PowerShell] release the leases ---------------------------------------------------------------------
python brain/tools/brain.py --as conantkd release
