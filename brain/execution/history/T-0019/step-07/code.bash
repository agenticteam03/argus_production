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
# 2026-10-12, conantkd. T-0019 batch 3c step 01 — the network verbs on both VMs, then the model on the dependency
#   cases.   [~35 min]
# Why: `network.connectivity` is a new read-gateway route and `/tcp` takes `attempts` (network probe): both target
#      services change on both hosts, and vm-095's agent image gets the capability. Verified before the merge, as
#      batch 2 was. Lease: both (session 66378486227b).
# MUTATES: the checkout + DEPLOYED marker on both VMs; the target services rebuilt (read gateway, network probe); on
#          vm-095 one backup and agent, worker and scheduler recreated together. One results file of the evaluation.
# ROLLBACK: deploy.sh main --as conantkd, then the same compose commands.
# =====================================================================================

# --- C.1 [VM vm-166 · bash] then [VM vm-095 · bash]: the branch, the target services (and the agent on vm-095) ------
ME=conantkd; BR=task/T-0019-batch3c-network-verbs
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
H=$(hostname | sed 's/^argus-//'); case $H in vm095) V=vm-095; O=compose.core-join.yml;; *) V=vm-166; O=compose.loopback.yml;; esac
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
[ $V = vm-095 ] && sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME | tail -1
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file $V.env -f compose.target.yml -f $O up -d --build 2>&1 | grep -c -E "Started|Running" | sed 's/^/target services up: /'
if [ $V = vm-095 ]; then
  cd /opt/argus-v18/app/deploy/vm-095
  sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
  for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f '{{.Image}}' $c | cut -c8-19) $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c)"; done
  sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
  sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py | grep -E "checks passed|FAIL"
  sudo bash /opt/argus-v18/app/ops/write-gate-check.sh | tail -1
fi
cd ~
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; NO INTERFERENCE; [vm-095: BACKUP OK]; DEPLOY OK (the branch); target services up;
#   vm-095: one image, running restarts=0, health 200, 20/20, 55/55, WRITE GATE CLOSED; LAB BASELINE OK; NO INTERFERENCE.

# --- C.2 [VM vm-166 · bash] the new routes from the host (loopback ports; counts and names only) --------------------
T=$(sudo cat /opt/argus-v18/secrets/docker_read_token); N=$(sudo cat /opt/argus-v18/secrets/network_probe_token)
g() { echo "$2 -> $(curl -s -o /tmp/r.json -w '%{http_code}' --max-time 20 -H "Authorization: Bearer $1" "http://127.0.0.1:$2") $(python3 -c 'import json,sys; d=json.load(sys.stdin); print({k: d.get(k) for k in ("from","to","shared","ok","succeeded","error")})' < /tmp/r.json 2>/dev/null)"; }
g "$T" "18701/connectivity?from=argus-lab-api&to=argus-lab-cache"
g "$T" "18701/connectivity?from=argus-lab-api&to=argus-lab-db"
g "$T" "18701/connectivity?from=argus-lab-api&to=argus-lab-nope"
g "$T" "18701/connectivity?from=argus-lab-api&to=argus-lab-api"
g "$N" "18703/tcp?host=argus-lab-cache&port=6379&attempts=3"
g "$N" "18703/tcp?host=argus-lab-cache&port=6379"
g "$N" "18703/tcp?host=argus-lab-cache&port=6379&attempts=6"
rm -f /tmp/r.json; unset T N
# Expected: api->cache 200 shared [argus-lab-app]; api->db 200 shared [argus-lab-app]; ->nope 404; ->itself 400;
#   tcp attempts=3 ok True succeeded 3; one attempt ok True succeeded 1; attempts=6 400. No address in any answer.

# --- C.3 [VM vm-095 · bash] the agent's code path (tools process, the tokens are there; no model) -----------------
sudo docker exec -u 10011 argus-v18-worker python -c "
from argus.domain.model import TargetRef
from argus.infrastructure.wiring import Settings, tools_dispatcher
specs, d, _ = tools_dispatcher(Settings())
for name, target, args in (('network.connectivity', 'vm-166/container:argus-lab-api', {'to': 'argus-lab-cache'}),
                           ('network.tcp_connect', 'vm-166/container:argus-lab-cache', {'port': 6379, 'attempts': 3})):
    s = next(x for x in specs if x.name == name)
    o = d.call(s, s.args_model.model_validate(args), TargetRef.parse(target))
    print(s.model_name, o.status, '|', o.model_text[:200])"
# Expected: check_connectivity ok | ... shared networks: argus-lab-app; check_tcp_connection ok | ... 3/3 connected (...)

# --- C.4 [VM vm-095 · bash] the model on the 55 cases, 5 trials (detached; compare with EVAL-3 step 2) --------------------------------
L=/opt/argus-v18/eval-results/T-0019-3c.log
sudo sh -c "nohup bash /opt/argus-v18/app/ops/eval-run.sh --as conantkd --trials 5 > $L 2>&1 &"
sudo tail -14 /opt/argus-v18/eval-results/T-0019-3c.log      # until the summary appears
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: dependency_unavailable as in EVAL-3 step 2 (1.00) or better, hard 0 0 0; NO INTERFERENCE.
