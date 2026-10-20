# (archived) DEPLOY-189 step 01, run 2026-10-20 by conantkd's agent over ssh; leases vm-095 + vm-166, session 7ae70b96a6ee.
# Ran as written (D.0 to D.3); D.4 (the browser click-through) is for a person. See evidence.md.
# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# DEPLOY-189 — redeploy vm-095 to main 2c7248b: T-0045 B6 (#184: /api/v1/target-metrics, /api/v1/overview), the B5
#   follow-up (#185: db-check proves 007), and the UI image built with VITE_ARGUS_INSIGHTS=1 (#164, never rebuilt
#   since: the Map and Metrics tabs, the Dashboard map)                                                    [~20 min]
# What changes: vm-095: the agent image (agent, worker, scheduler) and the UI image (the edge gains the two B6
#   locations). No migration (008 comes with B7, #188). vm-166: no change (its lease is held because the agent changes).
# MUTATES: vm-095.
# ROLLBACK: deploy.sh dfa7332 --as conantkd, then the two compose commands of D.1 and D.2.
# =====================================================================================

# --- D.0 [LAPTOP · PowerShell] both leases, then each VM's session marker --------------------------------------------
# DONE: both leases claimed until 2026-10-20T03:47Z, session 7ae70b96a6ee. Run this on BOTH VMs:
#   [VM vm-095 · bash] and [VM vm-166 · bash]
echo 'holder=conantkd session=7ae70b96a6ee' | sudo tee /opt/argus-v18/SESSION >/dev/null; cat /opt/argus-v18/SESSION

# --- D.1 [VM vm-095 · bash] state probe, backup, deploy, agent image (MUTATES) ----------------------------------------
ME=conantkd; BR=2c7248b
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
free -m | awk '/Mem/{print "mem available " $7 " MiB"}'
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "applied|REFUSED|schema:"
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
cd ~
# Expected: SESSION OK; ref=dfa7332, LAB BASELINE OK; NO INTERFERENCE; BACKUP OK; DEPLOY OK: 2c7248b; nothing new
#   applied (schema 001 to 007); three "Recreated".

# --- D.2 [VM vm-095 · bash] the UI image with Map and Metrics on (MUTATES) --------------------------------------------
cd /opt/argus-v18/app/deploy/ui
sudo docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml up -d --build </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
cd ~
for i in $(seq 1 30); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-v18-ui </dev/null 2>/dev/null); [ "$s" = healthy ] && break; sleep 3; done
echo "ui: $(sudo docker inspect -f '{{.State.Status}} health={{.State.Health.Status}} restarts={{.RestartCount}}' argus-v18-ui </dev/null) ports: $(sudo docker port argus-v18-ui </dev/null | tr '\n' ' ')"
echo "insights in bundle: $(sudo docker exec argus-v18-ui sh -c 'grep -l "api/v1/topology" /usr/share/nginx/html/assets/*.js | wc -l' </dev/null)"
# Expected: ui Recreated/Started, healthy restarts=0, ports 443 and 80 only; insights in bundle >= 1 (0 = the flag did
#   not reach the build: STOP).

# --- D.3 [VM vm-095 · bash] verification (read-only) --------------------------------------------------------------------
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f "{{.Image}}" $c </dev/null | cut -c8-19) $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
sudo docker logs --tail 8 argus-v18-agent 2>&1 </dev/null | grep -i -E "startup validation|threshold|error" || echo "agent: no startup errors"
sudo docker logs --tail 8 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
sudo docker exec argus-v18-agent python -c "import argus.application.target_metrics, argus.application.overview; print('B6 modules ok')" </dev/null
for p in /api/v1/overview "/api/v1/target-metrics?target=x/y:z" /api/v1/topology /api/v1/incidents/inc_smoke/metrics /api/v1/me /docs; do echo "GET $p $(curl -sk -o /dev/null -w '%{http_code}' "https://127.0.0.1$p" </dev/null)"; done
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
free -m | awk '/Mem/{print "mem available " $7 " MiB"}'
# Expected: health 200; the three on ONE image, restarts=0; no startup errors; 23/23 (#185's read included); B6 modules
#   ok; through the edge without a login every /api/v1 route 401 (404 = the old edge), /docs 404; 55/55; WRITE GATE
#   CLOSED; commit=2c7248b LAB BASELINE OK; NO INTERFERENCE.

# --- D.4 [BROWSER · by a person] the real-mode click-through -----------------------------------------------------------
# Log in to the public UI as an OPERATOR or APPROVER and check:
#   1. Dashboard: a "System map" card; unknown boxes/edges are dashed grey, never green.
#   2. An incident: the Map and Metrics tabs exist; Map shows the affected / root-cause boxes; Metrics draws the chart,
#      a missing sample is a gap and "fired" is red.
#   3. As a VIEWER: the incident Map shows the plain map (no overlay), no error.

# --- D.5 [LAPTOP · PowerShell] release the leases ----------------------------------------------------------------------
python brain/tools/brain.py --as conantkd release
