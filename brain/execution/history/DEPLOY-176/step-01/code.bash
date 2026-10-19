# (archived) DEPLOY-176 step 01, run 2026-10-19 by conantkd's agent over ssh; leases vm-095 + vm-166, session da7842d3a746.
# Ran as written (D.0 to D.2). An earlier attempt the same day, prepared for 77002a7, was not run (not authorized then);
#   this run is for main dfa7332. See evidence.md.
# =====================================================================================
# DEPLOY-176 — redeploy vm-095 to main dfa7332 (T-0045 B1 to B5: #173, #177, #174, #175, #176, #181; ACR-0023 #179;
#   #183 review rule, #178 CI; the rest Brain only)                                                       [~15 min]
# What changes: vm-095: migration 007 (incident.parent_id), then the agent image (agent, worker, scheduler) and its config/. vm-166: no change (its
#   lease is held because the agent changes). MUTATES vm-095.
# ROLLBACK: deploy.sh 19b1085 --as conantkd, then the compose command below.
# =====================================================================================

# --- D.0 [LAPTOP · PowerShell] both leases, then each VM's session marker --------------------------------------------
python brain/tools/brain.py start --task DEPLOY-176 --vm both
#   [VM vm-095 · bash] and [VM vm-166 · bash]  echo 'holder=conantkd session=<id>' | sudo tee /opt/argus-v18/SESSION >/dev/null

# --- D.1 [VM vm-095 · bash] state probe, backup, deploy, migrate, rebuild (MUTATES) -----------------------------------
ME=conantkd; BR=dfa7332
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
free -m | awk '/Mem/{print "mem available " $7 " MiB"}'
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "applied|REFUSED|schema:"
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
# Expected: SESSION OK; NO INTERFERENCE; BACKUP OK; DEPLOY OK: dfa7332; 007 applied; three "Recreated".

# --- D.2 [VM vm-095 · bash] verification (read-only) --------------------------------------------------------------------
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f "{{.Image}}" $c </dev/null | cut -c8-19) $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
sudo docker logs --tail 8 argus-v18-agent 2>&1 </dev/null | grep -i -E "startup validation|threshold|error" || echo "agent: no startup errors"
sudo docker logs --tail 8 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
sudo docker exec argus-v18-agent python -c "import argus.application.thresholds, argus.application.incident_view; from argus.capabilities.catalog import LOG_SCAN; print('B1/B4 modules ok; ACR-0023 LOG_SCAN', len(LOG_SCAN))" </dev/null
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
free -m | awk '/Mem/{print "mem available " $7 " MiB"}'
# Expected: health 200; the three on ONE image, restarts=0; no startup errors; 22/22; B1/B4 modules ok, LOG_SCAN 6; 55/55;
#   WRITE GATE CLOSED; commit=dfa7332 LAB BASELINE OK; NO INTERFERENCE.
