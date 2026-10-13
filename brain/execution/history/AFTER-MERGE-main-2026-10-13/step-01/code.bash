# (archived) AFTER-MERGE of #113-#131 to main ad72617, run 2026-10-13 by conantkd (agent ran the blocks over ssh); both leases, session 38abbb604d92
# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
#   [VM vm-095 · bash]      ssh argus-vm095
#   [VM vm-166 · bash]      ssh argus-vm166
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated".
# =====================================================================================

# =====================================================================================
# 2026-10-13, conantkd. AFTER-MERGE of #113-#131 (#123 merged while A.1 ran): both VMs from task/T-0035-monitoring-heartbeat
#   239e1d6 to main ad72617.   [~30 min]
# Why: main now has T-0019 deny floor (#114), the redactor fix (#115), T-0035 (#116), T-0036 histories (#119),
#      T-0038 baseline (#120), T-0037 docker read verbs (#122), T-0040 trace (#125), T-0042 routing (#127), T-0043
#      missing scrape jobs (#128) and the E2E-8 runner (#131). Code difference 239e1d6 → ad72617: services/target/
#      service.py and deploy/target/config (both target services), the agent (argus/..., config/), and Prometheus's
#      config and rules (deploy/monitoring/prometheus-vm-*.yml, alerts.yml: both Prometheus). No model call here.
# T-0035 order: migration 006 is already applied (schema_migrations 001-006) and both VMs already run a scheduler
#      that filters the heartbeat and a Prometheus with the rule (239e1d6). Still: vm-095's scheduler first (A.1),
#      both Prometheus after (P.1).
# Lease: both (session 38abbb604d92, until 17:09 UTC).
# MUTATES: the checkout + DEPLOYED marker on both VMs; the target services rebuilt; on vm-095 one backup, migrations
#          (no-op expected) and agent, worker and scheduler recreated together; both Prometheus recreated.
# ROLLBACK: deploy.sh task/T-0035-monitoring-heartbeat --as conantkd, then the same compose commands.
# Order: M.1 → A.1 on vm-166 → A.1 on vm-095 → P.1 on vm-166 → P.1 on vm-095.
# =====================================================================================

# --- M.1 [LAPTOP · PowerShell] the session marker on both VMs ------------------------------------------------------
ssh argus-vm166 'echo holder=conantkd session=38abbb604d92 | sudo tee /opt/argus-v18/SESSION >/dev/null; cat /opt/argus-v18/SESSION'
ssh argus-vm095 'echo holder=conantkd session=38abbb604d92 | sudo tee /opt/argus-v18/SESSION >/dev/null; cat /opt/argus-v18/SESSION'
# Expected: twice  holder=conantkd session=38abbb604d92

# --- A.1 [VM vm-166 · bash] then [VM vm-095 · bash]: main, the target services (and the agent on vm-095) (MUTATES) --
ME=conantkd; BR=main
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
H=$(hostname | sed 's/^argus-//'); case $H in vm095) V=vm-095; O=compose.core-join.yml;; *) V=vm-166; O=compose.loopback.yml;; esac
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
[ $V = vm-095 ] && sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME | tail -1
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file $V.env -f compose.target.yml -f $O up -d --build 2>&1 | grep -c -E "Started|Running" | sed 's/^/target services up: /'
if [ $V = vm-095 ]; then
  sudo bash /opt/argus-v18/app/ops/db-migrate.sh | grep -E "applied|REFUSED|schema:"
  cd /opt/argus-v18/app/deploy/vm-095
  sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
  for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f '{{.Image}}' $c | cut -c8-19) $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c)"; done
  sudo docker logs --tail 5 argus-v18-worker 2>&1 | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
  sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
  sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py | grep -E "checks passed|FAIL"
  sudo bash /opt/argus-v18/app/ops/write-gate-check.sh | tail -1
fi
cd ~
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; NO INTERFERENCE (before); [vm-095: BACKUP OK; 006 already applied, schema 001-006];
#   DEPLOY OK ad72617 (main); target services up: N; vm-095: agent, worker, scheduler on ONE image, running
#   restarts=0, health 200, no startup errors, db checks all passed, phase3 checks passed, WRITE GATE CLOSED;
#   commit=ad72617... ref=main; LAB BASELINE OK; NO INTERFERENCE.
# VERDICT: both VMs → P.1. Anything else → STOP (rollback above) and paste it.

# --- P.1 [VM vm-166 · bash] then [VM vm-095 · bash]: Prometheus recreated (T-0035 rule, T-0043 config) (MUTATES) --
H=$(hostname | sed 's/^argus-//'); case $H in vm095) V=vm-095; OV=compose.core-join.yml;; *) V=vm-166; OV=compose.loopback.yml;; esac
cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file $V.env -f compose.monitoring.yml -f $OV up -d --force-recreate --no-deps argus-v18-prometheus </dev/null 2>&1 | tail -1; cd ~
sleep 45
sudo docker exec argus-v18-prometheus wget -qO- 'http://127.0.0.1:9090/api/v1/rules' | python3 -c 'import json,sys; g=json.load(sys.stdin)["data"]["groups"]; r=[x["name"] for y in g for x in y["rules"]]; print(len(r), "rules; heartbeat:", "ArgusMonitoringHeartbeat" in r)'
sudo docker exec argus-v18-prometheus wget -qO- 'http://127.0.0.1:9090/api/v1/targets' | python3 -c 'import json,sys; t=json.load(sys.stdin)["data"]["activeTargets"]; print("targets:", " ".join(sorted(x["labels"]["job"]+"="+x["health"] for x in t)))'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: N rules; heartbeat: True; every target =up; NO INTERFERENCE.
# VERDICT: both → paste M.1 to P.1. Next: E2E-8 step 2 (runs), then release.
