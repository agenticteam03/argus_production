# (archived) DEPLOY of #151/#153 to vm-095 (main 37822c9), run 2026-10-14 by juanbetancurm; lease vm-095, session f10105709128
# =====================================================================================
# 2026-10-14 ~17:30 UTC, juanbetancurm. DEPLOY: vm-095 to main 37822c9 (#151: the UI starts investigations and shows
#   host metrics; #153 record only). Adapted from conantkd's AFTER-MERGE-main-2026-10-14 blocks.
# What changes on vm-095: the agent image (API: investigate token, quotas, /targets, /host-metrics) with the worker and
#   scheduler (one image, recreated together), and the UI image (new pages; the edge allows the new routes).
#   vm-166 is not touched (no target-service change in #151/#153).
# Lease: vm-095 only. MUTATES vm-095. ROLLBACK: deploy.sh 70d9fd7 --as juanbetancurm, then the same compose commands.
# Order: D.1 (laptop) -> D.2 (vm-095) -> D.3 (vm-095) -> D.4 (laptop).
# =====================================================================================

# --- D.1 [LAPTOP · PowerShell] claim the vm-095 lease and write the VM's session marker -------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git rev-parse --show-toplevel
# brain.py needs a clean tree: keep a copy of this file, restore main's placeholder, claim, then put this file back.
Copy-Item brain\execution\current\code.bash ..\code.bash.deploy -Force
git checkout -- brain/execution/current/code.bash
python brain/tools/brain.py --as juanbetancurm start --task DEPLOY-151 --vm vm-095
Copy-Item ..\code.bash.deploy brain\execution\current\code.bash -Force
git fetch origin
$sid = (git show origin/session:session.json | ConvertFrom-Json).vms.'vm-095'.session_id
Write-Output ('session ' + $sid)
ssh argus-vm095 ('echo holder=juanbetancurm session=' + $sid + ' | sudo tee /opt/argus-v18/SESSION >/dev/null; cat /opt/argus-v18/SESSION')
# Expected: "main is up to date (37822c9)", the lease claimed for vm-095, then "holder=juanbetancurm session=<id>".
#   If brain.py says vm-095 is in use by someone, STOP.

# --- D.2 [VM vm-095 · bash] main, backup, agent + worker + scheduler (MUTATES) ---------------------------------------
ME=juanbetancurm; BR=main
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "applied|REFUSED|schema:"
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f '{{.Image}}' $c </dev/null | cut -c8-19) $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c </dev/null)"; done
sudo docker logs --tail 5 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
cd ~
# Expected: SESSION OK; NO INTERFERENCE; BACKUP OK; DEPLOY OK: 37822c9... (main); no migration to apply (schema 001-006);
#   agent, worker, scheduler on ONE image, running restarts=0; health 200; worker: no startup errors; 20/20; 55/55;
#   WRITE GATE CLOSED. Anything else: STOP (rollback above) and paste it.

# --- D.3 [VM vm-095 · bash] the UI image (public mode), then the new routes through the edge (MUTATES) ---------------
ME=juanbetancurm
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
cd /opt/argus-v18/app/deploy/ui
sudo docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml up -d --build </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 30); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-v18-ui </dev/null 2>/dev/null); [ "$s" = healthy ] && break; sleep 3; done
echo "ui: $(sudo docker inspect -f '{{.State.Status}} health={{.State.Health.Status}} restarts={{.RestartCount}}' argus-v18-ui </dev/null) ports: $(sudo docker port argus-v18-ui </dev/null | tr '\n' ' ')"
cd ~
for p in /api/v1/targets /api/v1/host-metrics /api/v1/me /docs; do echo "GET $p $(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1$p </dev/null)"; done
echo "POST /api/v1/investigations $(curl -sk -o /dev/null -w '%{http_code}' -X POST https://127.0.0.1/api/v1/investigations </dev/null)"
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: ui running health=healthy restarts=0, ports 443 and 80 only; GET /api/v1/targets 401, /host-metrics 401,
#   /me 401 (they exist and need a login; 404 would mean the old edge), /docs 404; POST /api/v1/investigations 401;
#   commit=37822c9... ref=main; LAB BASELINE OK; NO INTERFERENCE.

# --- D.4 [LAPTOP · PowerShell] release the lease (after the smoke test in the UI, or now if you test later) --------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
python brain/tools/brain.py --as juanbetancurm release --vm vm-095
# VERDICT: DONE if D.2 and D.3 match. Then the UI smoke test (agent's note) and a record PR of this deployment.
