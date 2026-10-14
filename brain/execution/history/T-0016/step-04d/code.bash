# (archived) T-0016 step 4d, run 2026-10-14 by conantkd's agent over ssh; both leases, session fb04b6238725
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#   [VM vm-095 · bash] ssh argus-vm095   ·   [LAPTOP · bash] the tunnel test
# =====================================================================================
# A.1 [VM vm-095 · bash] the branch, and agent/worker/scheduler recreated together (MUTATES; rollback: deploy.sh main)
ME=conantkd; BR=task/T-0016-playwright
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f '{{.Image}}' $c </dev/null | cut -c8-19) $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c </dev/null)"; done
sudo docker logs --tail 5 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
cd ~
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1

# U.1 [VM vm-095 · bash] argus-v18-ui in loopback mode (MUTATES; rollback: docker compose -f compose.ui.yml -f compose.loopback.yml down)
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
cd /opt/argus-v18/app/deploy/ui
start=$(date +%s)
sudo docker compose -f compose.ui.yml -f compose.loopback.yml up -d --build </dev/null > /tmp/ui-build.log 2>&1; echo "compose exit=$? in $(( $(date +%s) - start )) s"
tail -3 /tmp/ui-build.log
for i in $(seq 1 30); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-v18-ui </dev/null 2>/dev/null); [ "$s" = healthy ] && break; sleep 3; done
echo "ui: $(sudo docker inspect -f '{{.State.Status}} health={{.State.Health.Status}} restarts={{.RestartCount}} user={{.Config.User}} ro={{.HostConfig.ReadonlyRootfs}}' argus-v18-ui </dev/null)"
echo "ports: $(sudo docker port argus-v18-ui </dev/null | tr '\n' ' ')"
echo "image: $(sudo docker images argus-v18-ui --format '{{.Tag}} {{.ID}} {{.Size}}' </dev/null | head -1)"
sudo ss -ltnH </dev/null | awk '{print $4}' | grep -E ':(18010|443|80)$' | tr '\n' ' '; echo "<- listeners on 18010/443/80"
cd ~
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1

# U.2 [LAPTOP · bash] the curl matrix through ssh -L 18011:127.0.0.1:18010 (read-only, no password; failed logins of a made-up user)
#!/bin/bash
# T-0016 4d U.2 [LAPTOP]: the curl matrix through ssh -L 18010 against the real API behind the edge (no password used).
set -u
ssh -o BatchMode=yes -o ExitOnForwardFailure=yes -N -L 18011:127.0.0.1:18010 argus-vm095 &
T=$!
trap 'kill $T 2>/dev/null' EXIT
for i in $(seq 1 20); do curl -s -o /dev/null http://127.0.0.1:18011/healthz && break; sleep 1; done
B=http://127.0.0.1:18011
c() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
echo "GET  /                         $(c $B/)"
echo "GET  /incidents/inc_x (SPA)    $(c $B/incidents/inc_x)"
echo "GET  /docs                     $(c $B/docs)"
echo "GET  /openapi.json             $(c $B/openapi.json)"
echo "GET  /api/v1/me (no token)     $(c $B/api/v1/me)"
echo "GET  /api/v1/incidents (no t.) $(c $B/api/v1/incidents)"
echo "POST /api/v1/investigations    $(c -X POST $B/api/v1/investigations)"
echo "GET  /api/v1/auth/token        $(c $B/api/v1/auth/token)"
echo "GET  /api/v1/approvals         $(c $B/api/v1/approvals)"
echo "GET  /runbooks/index.json      $(c $B/runbooks/index.json)"
echo "GET  /runbooks/ (bad token)    $(c -H 'Authorization: Bearer not-a-token' $B/runbooks/index.json)"
echo "headers: $(curl -sI $B/ | grep -iE '^(content-security-policy|x-frame-options|x-content-type-options|referrer-policy|server):' | cut -c1-40 | tr '\n' '|')"
JS=$(curl -s $B/ | grep -o 'assets/[^"]*\.js' | head -1)
echo "bundle: argus-demo=$(curl -s $B/$JS | grep -c argus-demo) runbook-text=$(curl -s $B/$JS | grep -c 'Container OOM restart loop') /runbooks/index.json-ref=$(curl -s $B/$JS | grep -c '/runbooks/index.json')"
U="edge-probe-$(date +%s)"
codes=""
for i in 1 2 3 4 5 6; do codes="$codes $(c -X POST -d "username=$U&password=x&scope=read" $B/api/v1/auth/token)"; done
echo "6 failed logins of $U through the edge: $codes"
echo "$U"
