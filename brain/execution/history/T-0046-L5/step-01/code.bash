# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# T-0046 L5 (2026-10-21) — vm-095 to main 2324186: link_states on (#234), a restart is no link transition (#231),
#   the gateway envelope is not a dropped field (#234), #232, #233. No migration; agent image only.     [~20 min]
# MUTATES: vm-095 (backup, checkout, agent image, one scheduler restart to prove `since` survives it). Both leases.
# ROLLBACK: link_states.enabled: false in deploy/scheduler/schedules.yaml and restart the scheduler, or
#   deploy.sh a4479df --as conantkd and the compose command of D.1. link_event rows stay (insert-only).
# =====================================================================================

# --- D.0 [LAPTOP · PowerShell] both leases, markers, then [VM vm-166 · bash] before ------------------------------------
python brain/tools/brain.py --as conantkd start --task T-0046-L5-deploy --vm both
#   [VM vm-095 · bash] and [VM vm-166 · bash]  echo 'holder=conantkd session=<id>' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^ref=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1

# --- D.1 [VM vm-095 · bash] probe, backup, deploy, rebuild (MUTATES) --------------------------------------------------
ME=conantkd; BR=2324186
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

# --- D.2 [VM vm-095 · bash] the recorder's first ticks (read-only) ----------------------------------------------------
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f "{{.Image}}" $c </dev/null | cut -c8-19) $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
sleep 75
sudo docker logs --since 10m argus-v18-scheduler 2>&1 </dev/null | grep -E "link states|rror" | tail -4
sudo docker exec argus-v18-agent argus db check </dev/null | grep -E "FAIL|checks passed"
sudo docker exec argus-v18-agent argus audit verify </dev/null | tail -1
sudo docker exec argus-v18-agent python -c '
from argus.infrastructure.wiring import Settings, make_store
s = make_store(Settings())
print("link_event rows by state:", dict(s._q("SELECT state, count(*) FROM link_event GROUP BY state ORDER BY state")))
print("links recorded:", s._q("SELECT count(DISTINCT (owner, dependency)) FROM link_event")[0][0])
print("transitions (latest_link_events):", len(s.latest_link_events()))
' </dev/null

# --- D.3 [VM vm-095 · bash] one scheduler restart: a row per link again, `since` unchanged (MUTATES: a restart) -------
sudo docker restart argus-v18-scheduler </dev/null >/dev/null; sleep 90
sudo docker logs --since 2m argus-v18-scheduler 2>&1 </dev/null | grep -E 'link states: [0-9]+ link' | tail -2
#   then the D.2 python block again: rows grow by one per link, latest_link_events' `at` is unchanged

# --- D.4 [VM vm-095 · bash] and [VM vm-166 · bash] after, then [LAPTOP] release ---------------------------------------
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
python brain/tools/brain.py --as conantkd release
