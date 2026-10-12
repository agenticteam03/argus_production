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
# 2026-10-12, conantkd. T-0019 batch 3b step 08 — the host verbs under the inspection policy on both VMs.  [~25 min]
# Why: the host probe gets four routes and its rendered config the inspection policy (3a); vm-095's agent gets four
#      Level 3 capabilities. Verified before the merge (branch stacked on 3a, #98). The VMs leave the 3c branch
#      (verified in step 07); after #98, #101 and this PR merge, AFTER-MERGE brings everything to main.
# MUTATES: the checkout + DEPLOYED marker on both VMs; the target services rebuilt; on vm-095 one backup and agent,
#          worker and scheduler recreated together.
# ROLLBACK: deploy.sh main --as conantkd, then the same compose commands.   Lease: both (session 66378486227b).
# =====================================================================================

# --- B.1 [VM vm-166 · bash] then [VM vm-095 · bash]: the branch, the target services (and the agent on vm-095) ------
ME=conantkd; BR=task/T-0019-batch3b-host-verbs
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

# --- B.2 [VM vm-166 · bash] the four routes from the host (loopback port 18702; contents not printed) --------------
T=$(sudo cat /opt/argus-v18/secrets/host_probe_token)
id=$(sudo docker inspect -f '{{.Id}}' argus-v18-host-probe); cg=/sys/fs/cgroup/system.slice/docker-$id.scope
g() { echo "$1 -> $(curl -s -o /tmp/r.json -w '%{http_code}' --max-time 20 -H "Authorization: Bearer $T" "http://127.0.0.1:18702$1") $(python3 -c "$2" < /tmp/r.json 2>/dev/null)"; }
J='import json,sys; d=json.load(sys.stdin)'
g "/service_config?target=vm-166/container:argus-lab-nginx" "$J; f=d['files'][0]; print(f['path'], 'proxy_read_timeout 2s' in f['text'], 'truncated', f['truncated'])"
g "/service_config?target=vm-166/container:argus-lab-nginx&path=/etc/passwd" "$J; print(d.get('error'))"
g "/read_file?target=vm-166/host:vm-166&path=/var/log/syslog&lines=5" "$J; print(d.get('error'))"
g "/read_file?target=vm-166/host:vm-166&path=/opt/argus-v18/secrets/host_probe_token&lines=1" "$J; print(d.get('error'))"
g "/journal?target=vm-166/host:vm-166&unit=docker.service&lines=20" "$J; print(d['source'], d['program'], 'lines', len(d['lines']), 'all dockerd', all(' dockerd[' in x for x in d['lines']))"
g "/journal?target=vm-166/host:vm-166&unit=ssh.service&lines=5" "$J; print(d.get('error'))"
g "/journal?target=vm-166/host:vm-166&unit=docker.service&lines=201" "$J; print(d.get('error'))"
P=$(pgrep -o dockerd)
g "/process_details?target=vm-166/host:vm-166&pid=$P" "$J; print(d['name'], d['state'], 'threads', d['threads'], 'open_files', d['open_files'], 'limit', d['limits']['max_open_files'], sorted(k for k in d if k in ('cmdline','environ')))"
g "/process_details?target=vm-166/container:argus-lab-nginx&pid=$P" "$J; print(d.get('error'))"
echo "probe memory: peak=$(( $(cat $cg/memory.peak)/1048576 ))MiB oom_kill=$(awk '/^oom_kill /{print $2}' $cg/memory.events) restarts=$(sudo docker inspect -f '{{.RestartCount}}' argus-v18-host-probe)"
rm -f /tmp/r.json; unset T
# Expected: service_config 200 (default.conf, True, truncated False); /etc/passwd 403; read_file 403 twice (files is
#   empty); journal 200 syslog dockerd, all dockerd True; ssh.service 403; lines=201 400; process_details 200 dockerd
#   with threads, open_files and a limit, [] (no cmdline/environ); on the nginx target 403; peak well under 64 MiB,
#   oom_kill 0, restarts 0.

# --- B.3 [VM vm-095 · bash] the agent's code path (tools process, no model) ---------------------------------------
sudo docker exec -u 10011 argus-v18-worker python -c "
from argus.domain.model import TargetRef
from argus.infrastructure.wiring import Settings, tools_dispatcher
specs, d, _ = tools_dispatcher(Settings())
for name, target, args in (('host.service_config', 'vm-166/container:argus-lab-nginx', {}),
                           ('host.journal', 'vm-095/host:vm-095', {'unit': 'docker.service', 'lines': 5})):
    s = next(x for x in specs if x.name == name)
    o = d.call(s, s.args_model.model_validate(args), TargetRef.parse(target))
    print(s.model_name, o.status, '|', o.model_text[:220].replace(chr(10), ' / '))"
# Expected: inspect_service_config ok | ... proxy_read_timeout 2s ...; get_journal_logs ok | journal of docker.service on
#   vm-095/host:vm-095 (syslog, program dockerd): N line(s) ...  (the policy engine is not in this path: the dispatcher
#   is below InvokeCapability; the probe's own check is what answers here).
