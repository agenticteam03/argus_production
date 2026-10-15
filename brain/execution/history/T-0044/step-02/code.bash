# (archived) T-0044 step 2, run 2026-10-15 by conantkd's agent over ssh; leases vm-095 + vm-166, session cd8044e6d88e. All blocks as written.
# =====================================================================================
# T-0044 step 2 (2026-10-15, conantkd): vm-095 on the PR branch task/T-0044-weaviate-rag (#157); argus-v18-weaviate
#   started; the index built from the worker with real embeddings; the hybrid compared with TF-IDF per class.
# What changes: vm-095 only. The agent image (the RAG code), a new container argus-v18-weaviate + volume. The worker
#   stays ARGUS_RETRIEVAL=tfidf: investigations do not use the hybrid in this step. vm-166 not touched.
# Leases: vm-095 + vm-166 (the agent changes). MUTATES vm-095.
# ROLLBACK: deploy.sh main --as conantkd, the R.2 compose command for the three; stop and remove argus-v18-weaviate
#   (`docker compose ... rm -sf argus-v18-weaviate`, `docker volume rm argus-v18-weaviate-data`).
# =====================================================================================

# --- R.0 [LAPTOP · PowerShell] both leases, then each VM's marker ----------------------------------------------------
python brain/tools/brain.py start --task T-0044 --vm both
#   [VM vm-095 · bash] and [VM vm-166 · bash]  echo 'holder=conantkd session=<id>' | sudo tee /opt/argus-v18/SESSION >/dev/null

# --- R.1 [VM vm-095 · bash] state probe (read-only) ------------------------------------------------------------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
free -m | awk 'NR==2{print "mem available="$7" MiB"}'; awk 'NR==1{print "io "$2}' /proc/pressure/io
# Expected: commit=1d222ad (or 5d4b347) ref=main, LAB BASELINE OK, NO INTERFERENCE, about 4 GiB available.

# --- R.2 [VM vm-095 · bash] the branch, Weaviate, the core recreated (MUTATES) --------------------------------------
ME=conantkd; BR=task/T-0044-weaviate-rag
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --no-deps argus-v18-weaviate </dev/null 2>&1 | grep -E "Created|Started|Error" | tr '\n' ' '; echo
for i in $(seq 1 30); do c=$(sudo docker exec argus-v18-worker python -c "import urllib.request;print(urllib.request.urlopen('http://argus-v18-weaviate:8080/v1/.well-known/ready',timeout=3).status)" 2>/dev/null </dev/null); [ "$c" = 200 ] && break; sleep 2; done; echo "weaviate ready (from the worker) $c"
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler argus-v18-weaviate; do echo "$c $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c </dev/null)"; done
sudo docker exec argus-v18-worker sh -c 'echo retrieval=$ARGUS_RETRIEVAL weaviate=$ARGUS_WEAVIATE_URL' </dev/null
sudo docker logs --tail 5 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo docker port argus-v18-weaviate </dev/null | wc -l | sed 's/^/weaviate host ports: /'
cd ~
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: BACKUP OK; DEPLOY OK (the branch); weaviate ready 200 from the worker; the three recreated, health 200,
#   restarts=0; retrieval=tfidf; no startup errors; 20/20; 55/55; WRITE GATE CLOSED; weaviate host ports: 0;
#   LAB BASELINE OK; NO INTERFERENCE (no new listener: Weaviate publishes no host port).

# --- R.3 [VM vm-095 · bash] build the index from the worker (real embeddings; MUTATES the index only) --------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
time sudo docker exec argus-v18-worker python -m argus runbooks index </dev/null
sudo docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' argus-v18-weaviate argus-v18-worker
# Expected: "indexed N sections of 21 runbooks (...) into RunbookPassage ...; N objects stored", in well under a minute.

# --- R.4 [VM vm-095 · bash] the hybrid beside TF-IDF, per class (read-only) -----------------------------------------
q() { sudo docker exec -e ARGUS_RETRIEVAL=hybrid argus-v18-worker python -m argus runbooks search "$1" --runbooks "$2" --compare </dev/null; echo; }
q "health_check_failed health check reports unhealthy api returns errors" RB-002,RB-003
q "container_restart_loop restarts in 10 min OOM killed keeps restarting" RB-001,RB-008
q "container_restart_loop restarts in 10 min exit code 1 crash keeps restarting" RB-001,RB-008
q "dependency_unavailable dependency probe failed shares no network api returns errors" RB-003,RB-004,RB-009
q "postgresql_connection_exhaustion connections used near the limit clients cannot get a database connection" RB-004,RB-013
q "disk_pressure disk used ratio hours to full the disk is almost full" RB-005,RB-019
q "cpu_saturation cpu cores busy the service is slow" RB-006
q "nginx_upstream_failure gateway error ratio users see 504" RB-015,RB-002,RB-003
q "monitoring_blind_spot scrape targets down no fresh samples" RB-014
sudo docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' argus-v18-weaviate
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: each query answers from the hybrid (no "fell back" line) and from TF-IDF; NO INTERFERENCE.

# --- R.9 [LAPTOP · PowerShell] release both leases ------------------------------------------------------------------
python brain/tools/brain.py release
