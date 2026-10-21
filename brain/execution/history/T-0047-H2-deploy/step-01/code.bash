# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# T-0047 H2/H3 deploy (2026-10-21) — vm-095 to main 6c83da3: migration 012 incident_hypothesis (#236), the ranking
#   and the context slot (#236), the hypotheses in the incident answer (#237). Migration before the image. [~20 min]
# MUTATES: vm-095 (backup, checkout, migration 012, agent image). Both leases. vm-166: no change.
# ROLLBACK: deploy.sh 2324186 --as conantkd and the compose command of D.1; migration 012 stays (the old image does
#   not read incident_hypothesis).
# =====================================================================================

# --- D.0 [LAPTOP · PowerShell] both leases, markers, then [VM vm-166 · bash] before ------------------------------------
python brain/tools/brain.py --as conantkd start --task T-0047-H2-deploy --vm both
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1

# --- D.1 [VM vm-095 · bash] probe, backup, deploy, migrate 012, rebuild (MUTATES) -------------------------------------
ME=conantkd; BR=6c83da3
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -2
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "\+ |REFUSED|schema:"
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
cd ~
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"

# --- D.2 [VM vm-095 · bash] verification (read-only) ------------------------------------------------------------------
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f "{{.Image}}" $c </dev/null | cut -c8-19) $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do n=$(sudo docker logs --since 10m $c 2>&1 </dev/null | grep -ciE "traceback|error"); echo "$c error lines: $n"; done
sudo docker exec argus-v18-agent argus db check </dev/null | grep -E "FAIL|checks passed"
sudo docker exec argus-v18-agent argus audit verify </dev/null | tail -2
for p in /api/v1/topology /api/v1/me /docs; do echo "GET $p $(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1$p </dev/null)"; done
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
sudo docker exec argus-v18-agent python -c '
from argus.infrastructure.wiring import Settings, make_store
s = make_store(Settings())
print("incident_hypothesis rows:", s._q("SELECT count(*) FROM incident_hypothesis")[0][0])
' </dev/null
sudo docker logs --since 5m argus-v18-worker 2>&1 </dev/null | grep -ciE "traceback|ranking" | sed "s/^/worker traceback-or-ranking lines: /"

# --- D.3 [VM vm-166 · bash] after, then [LAPTOP] release ---------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
python brain/tools/brain.py --as conantkd release
