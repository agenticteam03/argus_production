# (archived) AFTER-MERGE of #141, #144-#147 to main, run 2026-10-14 by conantkd's agent over ssh; both leases, session dc432c3ff537
# Order: A.1 vm-166 -> A.1 vm-095 -> (502 found) reload -> the resolver fix -> U.1 vm-095
# A.1 [VM vm-166 · bash] then [VM vm-095 · bash] (MUTATES; rollback: deploy.sh task/T-0016-playwright on vm-095, ad72617 on vm-166)
ME=conantkd; BR=main
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
H=$(hostname | sed 's/^argus-//'); case $H in vm095) V=vm-095; O=compose.core-join.yml;; *) V=vm-166; O=compose.loopback.yml;; esac
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
[ $V = vm-095 ] && sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file $V.env -f compose.target.yml -f $O up -d --build </dev/null 2>&1 | grep -c -E "Started|Running" | sed 's/^/target services up: /'
if [ $V = vm-095 ]; then
  sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "applied|REFUSED|schema:"
  cd /opt/argus-v18/app/deploy/vm-095
  sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
  for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f '{{.Image}}' $c </dev/null | cut -c8-19) $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c </dev/null)"; done
  sudo docker logs --tail 5 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
  sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
  sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
  sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
  sudo docker exec -u 10011 argus-v18-worker python -c "from argus.detectors.classes import CLASSES; print('strategies:', {c.name: c.strategy for c in CLASSES if c.name in ('dependency_unavailable','nginx_upstream_failure','health_check_failed')})" </dev/null
  echo "ui: $(sudo docker inspect -f '{{.State.Status}} health={{.State.Health.Status}} restarts={{.RestartCount}}' argus-v18-ui </dev/null) ports: $(sudo docker port argus-v18-ui </dev/null | tr '\n' ' ')"
fi
cd ~
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1

# R.1 [VM vm-095 · bash] the edge answered 502 on /api/v1/me after the agent was recreated: reload (re-resolves the name)
sudo docker exec argus-v18-ui nginx -s reload

# U.1 [VM vm-095 · bash] the resolver fix: the edge rebuilt, then the agent recreated WITHOUT reloading the edge (MUTATES)
ME=conantkd; BR=task/AFTER-MERGE-main-2026-10-14
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
cd /opt/argus-v18/app/deploy/ui
sudo docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml up -d --build </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 30); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-v18-ui </dev/null 2>/dev/null); [ "$s" = healthy ] && break; sleep 3; done
echo "ui: $(sudo docker inspect -f '{{.State.Status}} health={{.State.Health.Status}} restarts={{.RestartCount}}' argus-v18-ui </dev/null)"
sudo docker exec argus-v18-ui grep -c "resolve;" /etc/nginx/argus/http.conf </dev/null | sed 's/^/upstream resolve lines: /'
agent_ip() { sudo docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' argus-v18-agent </dev/null; }
echo "agent address before: $(agent_ip)"
# the scenario that gave 502: the agent recreated (a new address), the edge NOT reloaded
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --force-recreate --no-deps argus-v18-agent </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "agent health $c, address after: $(agent_ip)"
cd ~
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)='
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
