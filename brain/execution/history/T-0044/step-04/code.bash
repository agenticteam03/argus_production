# (archived) T-0044 step 4: the task is SUSPENDED (2026-10-15, conantkd): vm-095 back to main, Weaviate removed.
# Run by conantkd's agent over ssh; leases vm-095 + vm-166, session 0ec3a32ee8cd.
# Why: the team improves the runbook corpus and the eval cases first (§15.3, §21.2); the retriever waits.
# What changes: vm-095 only. argus-v18-weaviate and its volume removed (the index is derived: `argus runbooks index`
#   rebuilds it); vm-095 on main 1d222ad; agent, worker, scheduler recreated on main's image. vm-166 not touched.
# ROLLBACK (resume the task): deploy.sh task/T-0044-weaviate-rag, compose up argus-v18-weaviate and the three,
#   `argus runbooks index` in the worker (T-0044 step 2).

# --- S.1 [VM vm-095 · bash] (MUTATES) ---------------------------------------------------------------------------------
ME=conantkd; BR=main
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo docker rm -f argus-v18-weaviate </dev/null >/dev/null && echo "weaviate container removed"
sudo docker volume rm argus-v18-weaviate-data </dev/null >/dev/null && echo "weaviate volume removed"
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f '{{.Image}}' $c </dev/null | cut -c8-19) $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c </dev/null)"; done
sudo docker logs --tail 5 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo docker ps -a --format '{{.Names}}' | grep -c weaviate | sed 's/^/weaviate containers left: /'
cd ~
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: BACKUP OK; weaviate removed; DEPLOY OK: 1d222ad (main); the three on one image, health 200, restarts=0;
#   20/20; 55/55; WRITE GATE CLOSED; 0 weaviate containers; commit=1d222ad ref=main; LAB BASELINE OK; NO INTERFERENCE.
