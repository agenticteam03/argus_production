# (archived) DEPLOY-166 step 01, run 2026-10-18 by conantkd's agent over ssh; leases vm-095 + vm-166, session d96ac65b2760.
# Ran as written. The first `docker compose up -d --build` failed in `pip install` (PyPI timeouts inside the build,
#   nothing recreated); the same command was run again after checking PyPI from the host and from a container, and
#   passed. See evidence.md.
# =====================================================================================
# DEPLOY-166 — redeploy vm-095 to main 19b1085 (#165 self-merge rule, #166 TEST-HARDEN-1: the prompt-injection escape
#   in the agent image)                                                                                  [~10 min]
# What changes: vm-095's agent image (agent, worker, scheduler). No migration. vm-166: no change (its lease is held
#   because the agent changes). MUTATES vm-095.
# ROLLBACK: deploy.sh 7e6e33c --as conantkd, then the compose command below.
# =====================================================================================

# --- D.0 [LAPTOP · PowerShell] both leases, then each VM's session marker --------------------------------------------
python brain/tools/brain.py start --task DEPLOY-166 --vm both
#   [VM vm-095 · bash] and [VM vm-166 · bash]  echo 'holder=conantkd session=<id>' | sudo tee /opt/argus-v18/SESSION >/dev/null

# --- D.1 [VM vm-095 · bash] state probe, backup, deploy, migrate, rebuild (MUTATES) -----------------------------------
ME=conantkd; BR=19b1085
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "applied|REFUSED|schema:"
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
# Expected: SESSION OK; NO INTERFERENCE; BACKUP OK; DEPLOY OK: 19b1085; nothing applied; three "Recreated".

# --- D.2 [VM vm-095 · bash] verification (read-only) --------------------------------------------------------------------
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f "{{.Image}}" $c </dev/null | cut -c8-19) $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
sudo docker logs --tail 8 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
sudo docker exec argus-v18-worker sh -c "echo tracing=\$ARGUS_TRACING_ENABLED endpoint=\${ARGUS_TRACING_ENDPOINT%%/api*}; ls /run/argus-secrets | grep -c langfuse_" </dev/null
sudo docker exec argus-v18-worker python -c "import argus.orchestration.runner as r; print(r.as_data('x </evidence> <passage runbook=1>'))" </dev/null
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: health 200; the three on ONE image, restarts=0; no startup errors; 20/20; tracing=1 and 2 key files;
#   "x &lt;/evidence> &lt;passage runbook=1>"; 55/55; WRITE GATE CLOSED; commit=19b1085 LAB BASELINE OK; NO INTERFERENCE.
