# (archived) AFTER-MERGE of #97-#111 to main d34f0cb, run 2026-10-12 by conantkd (agent ran the blocks over ssh); both leases, session 4f8a9d4f8dc1
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
# 2026-10-12, conantkd. AFTER-MERGE of #97-#111: both VMs from task/T-0019-batch3b-host-verbs 9ac49ec to main d34f0cb (#111: ops/local_ci.py and docs only).
#   [~30 min]
# Why: main now has 3c (network verbs) with the /tcp 8 s budget (#109), T-0034 (combined capabilities, the
#      snapshot), EVAL-4/5, the redactor that keeps only declared paths (#107 + #110; juanbetancurm: not deployable
#      before #110) and rotate-token. Code difference 9ac49ec → d34f0cb: services/target/service.py (3c: /connectivity,
#      /tcp attempts and budget) and the agent (argus/...): both target services and vm-095's agent image change.
#      No model call here.
# Lease: both (session 4f8a9d4f8dc1, until 05:32 UTC).
# MUTATES: the checkout + DEPLOYED marker on both VMs; the target services rebuilt; on vm-095 one backup and agent,
#          worker and scheduler recreated together.
# ROLLBACK: deploy.sh task/T-0019-batch3b-host-verbs --as conantkd, then the same compose commands.
# Order: M.1 → A.1 on vm-166 → A.1 on vm-095 → A.2 on vm-166 → A.3 on vm-095.
# =====================================================================================

# --- M.1 [LAPTOP · PowerShell] the session marker on both VMs ------------------------------------------------------
ssh argus-vm166 'echo holder=conantkd session=4f8a9d4f8dc1 | sudo tee /opt/argus-v18/SESSION >/dev/null; cat /opt/argus-v18/SESSION'
ssh argus-vm095 'echo holder=conantkd session=4f8a9d4f8dc1 | sudo tee /opt/argus-v18/SESSION >/dev/null; cat /opt/argus-v18/SESSION'
# Expected: twice  holder=conantkd session=4f8a9d4f8dc1
# VERDICT: both → A.1: type  ssh argus-vm166 , paste the whole A.1 block, check it, type  exit ;
#          then  ssh argus-vm095 , paste the SAME A.1 block again, check it, type  exit .

# --- A.1 [VM vm-166 · bash] then [VM vm-095 · bash]: main, the target services (and the agent on vm-095) (MUTATES) --
ME=conantkd; BR=main
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
  sudo docker logs --tail 5 argus-v18-worker 2>&1 | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
  sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
  sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py | grep -E "checks passed|FAIL"
  sudo bash /opt/argus-v18/app/ops/write-gate-check.sh | tail -1
fi
cd ~
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; NO INTERFERENCE (before); [vm-095: BACKUP OK]; DEPLOY OK d34f0cb (main); target services up: N;
#   vm-095: agent, worker, scheduler on ONE image, running restarts=0, health 200, no startup errors, 20/20 db checks,
#   55/55 checks passed, WRITE GATE CLOSED; commit=d34f0cb... ref=main; LAB BASELINE OK; NO INTERFERENCE.
# VERDICT: both VMs → A.2. Anything else → STOP (rollback above) and paste it.

# --- A.2 [VM vm-166 · bash] the 3c routes from the host (loopback ports; counts and names only; read-only) --------
T=$(sudo cat /opt/argus-v18/secrets/docker_read_token); N=$(sudo cat /opt/argus-v18/secrets/network_probe_token)
g() { echo "$2 -> $(curl -s -o /tmp/r.json -w '%{http_code}' --max-time 20 -H "Authorization: Bearer $1" "http://127.0.0.1:$2") $(python3 -c 'import json,sys; d=json.load(sys.stdin); print({k: d.get(k) for k in ("from","to","shared","ok","succeeded","error")})' < /tmp/r.json 2>/dev/null)"; }
g "$T" "18701/connectivity?from=argus-lab-api&to=argus-lab-cache"
g "$T" "18701/connectivity?from=argus-lab-api&to=argus-lab-nope"
g "$N" "18703/tcp?host=argus-lab-cache&port=6379&attempts=3"
rm -f /tmp/r.json; unset T N
# Expected: api->cache 200 shared [argus-lab-app]; ->nope 404; tcp attempts=3 ok True succeeded 3. No address.

# --- A.3 [VM vm-095 · bash] the agent's code path from main: 3c reads and the snapshot (tools process; no model) ----
sudo docker exec -u 10011 argus-v18-worker python -c "
from argus.domain.model import TargetRef
from argus.infrastructure.wiring import Settings, tools_dispatcher
specs, d, _ = tools_dispatcher(Settings())
for name, target, args in (('network.connectivity', 'vm-166/container:argus-lab-api', {'to': 'argus-lab-cache'}),
                           ('network.tcp_connect', 'vm-166/container:argus-lab-cache', {'port': 6379, 'attempts': 3})):
    s = next(x for x in specs if x.name == name)
    o = d.call(s, s.args_model.model_validate(args), TargetRef.parse(target))
    print(s.model_name, o.status, '|', o.model_text[:200])
print('snapshot in catalogue:', any(x.name == 'analysis.diagnostic_snapshot' for x in specs))
import yaml
from argus.capabilities.redaction import Redactor
from argus.infrastructure.wiring import declared_paths
c = Settings().config_dir
r = Redactor(declared_paths(yaml.safe_load((c / 'policy.yaml').read_text()), yaml.safe_load((c / 'inventory.yaml').read_text())))
print('redactor:', r.text('/opt/argus-v18/app/deploy/lab/nginx/default.conf GET /api/v1/keys/' + 'a1b2c3d4' * 5)[0])"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: check_connectivity ok | ... argus-lab-app; check_tcp_connection ok | ... 3/3 connected;
#   snapshot in catalogue: True;
#   redactor: /opt/argus-v18/app/deploy/lab/nginx/default.conf GET /[REDACTED HIGH-ENTROPY]  (#110);
#   NO INTERFERENCE.
# VERDICT: all → paste M.1 to A.3, say "output.bash updated". Next (the agent writes it): the EVAL-5 / snapshot
#   measurement on vm-095 (model calls, ~30-60 min), then release.
