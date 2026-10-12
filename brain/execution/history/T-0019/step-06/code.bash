# (archived) T-0019 batch 2 step 03 (history step-06), run 2026-10-12 by the agent over SSH (sessions cd4367edd721 / 7a5515db6285)
# S3.1 as archived is its second version (curl from the host); the first ran the checks with docker exec inside the
# probe and OOM-killed it (evidence row 1).
# T-0019 batch 2, step 03 — deploy the host-probe verbs on both VMs and the agent on vm-095; verify   [~20 min]
# Why: the six new routes live in argus-v18-host-probe (same image on both hosts); the agent needs the new
#      capabilities and policy lines. Verify each route on the host itself, then through the agent's own code path
#      (capability → executor → token → tunnel → redaction), and that nothing else changed.
# MUTATES: vm-166 and vm-095: checkout of task/T-0019-batch2-host-probe; argus-v18-target:1 rebuilt and the target
#          services recreated (no new mount, privilege or token). vm-095: argus-v18-agent rebuilt. No lab container
#          changes. No model call.
# Undo: on each VM `deploy.sh main` + the same target `up -d --build`; on vm-095 the agent rebuild (main does not
#       know the new capabilities; the probe's extra routes are then simply unused).
# Leases: conantkd, vm-166 (session cd4367edd721) and vm-095 (session 7a5515db6285).
# =====================================================================================

# --- S3.1 [VM vm-166 · bash] (ssh argus-vm166) checkout + target services + the routes on the host (MUTATES) -------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0019-batch2-host-probe --as $ME | tail -2
cd /opt/argus-v18/app/deploy/target
sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml up -d --build 2>&1 | tail -6; cd ~
sleep 15
sudo docker ps --format '{{.Names}}\t{{.Status}}' | grep -E '^argus-v18-' | sort
# every route from the host through the loopback port (no exec: it would add its own memory to the probe's cgroup),
# with the probe's cgroup memory after each; then the two heaviest routes twice in parallel. Counts only.
id=$(sudo docker inspect -f '{{.Id}}' argus-v18-host-probe); cg=/sys/fs/cgroup/system.slice/docker-$id.scope
mem() { echo "cur=$(( $(cat $cg/memory.current)/1048576 ))MiB peak=$(( $(cat $cg/memory.peak)/1048576 ))MiB oom_kill=$(awk '/^oom_kill /{print $2}' $cg/memory.events)"; }
T=$(sudo cat /opt/argus-v18/secrets/host_probe_token)
q() { s=$(date +%s%N); c=$(curl -s -o /tmp/hp.json -w '%{http_code}' --max-time 20 -H "Authorization: Bearer $T" "http://127.0.0.1:18702$1")
      echo "$1 -> $c $(( ($(date +%s%N)-s)/1000000 )) ms | $(python3 -c "$2" < /tmp/hp.json 2>/dev/null) | $(mem)"; }
J='import json,sys; d=json.load(sys.stdin)'
echo "start: $(mem)"
q /load "$J; print(d['load1'], d['load5'], d['load15'], 'runnable', d['runnable'], 'psi_io', d['pressure']['io'])"
q /io "$J; print([(x['device'], x['busy_percent'], x['write_kib_s']) for x in d['devices']])"
for by in cpu memory; do q "/processes?by=$by&n=5" "$J; r=d['processes']; print('rows', len(r), 'pids_read', d['pids_read'], 'in_containers', sum(1 for p in r if p['container_id']), 'keys', sorted({k for p in r for k in p}))"; done
q "/processes?by=disk" "print('-')"
q /sockets "$J; print(d['namespace'], d['tcp_by_state'], 'listening', d['listening_ports_total'])"
q "/directory_sizes?path=/srv/argus-lab-fill" "$J; print('children', d['children_read'], 'complete', d['complete'])"
q "/directory_sizes?path=/" "$J; print('children', d['children_read'], 'entries', d['entries_read'], 'complete', d['complete'], 'other_fs', d['other_filesystems'])"
q "/directory_sizes?path=/etc" "print('-')"
q "/oom?minutes=60" "$J; print(d['source'], 'records', d['records_total'], 'complete', d['complete'])"
q "/oom?minutes=1440" "$J; print(d['source'], 'records', d['records_total'], 'complete', d['complete'], 'since_boot', d['oom_kill_since_boot'])"
for i in 1 2; do
  for p in "/directory_sizes?path=/" "/oom?minutes=1440" "/directory_sizes?path=/" "/oom?minutes=1440"; do
    curl -s -o /dev/null --max-time 30 -H "Authorization: Bearer $T" "http://127.0.0.1:18702$p" & done; wait
  echo "parallel round $i (2 walks + 2 OOM reads at once): $(mem)"
done
rm -f /tmp/hp.json; unset T
echo "probe: $(sudo docker inspect -f 'restarts={{.RestartCount}} status={{.State.Status}}' argus-v18-host-probe)"
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; DEPLOY OK; the target services Up; load/io/top/sockets/dirs/oom 200, by=disk 400,
#           dirs /etc 400; top keys without cmdline/environ; dirs fill complete True; dirs / partial within ~4 s;
#           oom source kern.log; oom_kill stays 0 and the peak well under 64 MiB, also in the parallel rounds;
#           probe restarts=0; LAB BASELINE OK; NO INTERFERENCE.

# --- S3.2 [VM vm-095 · bash] (ssh argus-vm095) checkout + target services + agent + checks (MUTATES; no model) -----
ME=conantkd
echo "holder=$ME session=7a5515db6285" | sudo tee /opt/argus-v18/SESSION >/dev/null
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0019-batch2-host-probe --as $ME | tail -2
cd /opt/argus-v18/app/deploy/target
sudo docker compose --env-file vm-095.env -f compose.target.yml -f compose.core-join.yml up -d --build 2>&1 | tail -4
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent 2>&1 | tail -3; cd ~
for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz); echo "health $c"; [ "$c" = 200 ] && break; sleep 5; done
sudo docker logs --tail 5 argus-v18-agent 2>&1 | grep -i -E "startup validation|missing credential|error" || echo "no startup errors"
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py | grep -E "host probe|checks passed|FAIL"
sudo docker exec -i argus-v18-agent python - <<'PY'
# the agent's own code path for the seven new capabilities, on both hosts (no incident, no model)
from argus.adapters.outbound.config_adapters import YamlInventory
from argus.capabilities.catalog import build_catalog
from argus.capabilities.redaction import Redactor
from argus.domain.model import TargetRef
from argus.infrastructure.wiring import Settings
from argus.tooling.dispatch import Dispatcher
from argus.tooling.executors import ExecutorRegistry, TargetAgentClient
s = Settings()
inv = YamlInventory((s.config_dir / "inventory.yaml").read_text(encoding="utf-8"))
reg = ExecutorRegistry()
reg.register("host_probe", lambda url, tok: TargetAgentClient(url, tok))
tokens = {(h, "host_probe"): s.secret(f"{h}/host_probe_token") for h in ("vm-095", "vm-166")}
d = Dispatcher(inv, reg, tokens, Redactor())
specs = {x.name: x for x in build_catalog()}
for host, mount in (("vm-166", "/srv/argus-lab-fill"), ("vm-095", "/")):
    for name, args in (("host.load", {}), ("host.io", {}), ("host.top_cpu", {"n": 3}), ("host.top_memory", {"n": 3}),
                       ("host.socket_summary", {}), ("host.directory_sizes", {"mount": mount}),
                       ("host.kernel_oom_records", {"minutes": 60})):
        spec = specs[name]
        o = d.call(spec, spec.args_model.model_validate(args), TargetRef.parse(f"{host}/host:{host}"))
        text = o.model_text if name not in ("host.top_cpu", "host.top_memory") else f"{len(o.model_text)} chars"
        print(host, spec.model_name, "level", spec.level, o.status, "|", text[:230])
PY
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; DEPLOY OK; target services and agent recreated; health 200; no startup errors; every
#           phase3_check "host probe" line PASS and "N/N checks passed"; 14 capability lines status ok (Level 2),
#           texts with values or "unknown" (never a bare zero for a missing source); LAB BASELINE OK; NO INTERFERENCE.

# --- S3.3 [VM vm-095 · bash] (ssh argus-vm095) the agent's code path, where the tokens are (read-only, no model) ----
# Why: S3.2's snippet ran in argus-v18-agent, which since T-0021 holds no executor token (every read 401). The tokens
#      are in argus-v18-worker, readable only by its tools user (argus-tools, uid 10011): run the same dispatcher
#      the tools process uses (wiring.tools_dispatcher) as that user. No incident, no model, nothing written.
# First run: KeyError 'host.load': S3.2 rebuilt the image and recreated argus-v18-agent only; argus-v18-worker and
# argus-v18-scheduler run the same image and were still on the old code. MUTATES: both recreated on the new image
# (the worker finishes a running investigation first, stop_grace_period 120 s).
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --no-deps argus-v18-worker argus-v18-scheduler 2>&1 | tail -4; cd ~
sleep 10
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f '{{.Image}}' $c | cut -c8-19) $(sudo docker inspect -f '{{.State.Status}} started={{.State.StartedAt}}' $c)"; done
sudo docker logs --tail 5 argus-v18-worker 2>&1 | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
sudo docker exec -i -u 10011 argus-v18-worker python - <<'PY'
from argus.domain.model import TargetRef
from argus.infrastructure.wiring import Settings, tools_dispatcher
specs, d, _ = tools_dispatcher(Settings())
specs = {x.name: x for x in specs}
for host, mount in (("vm-166", "/srv/argus-lab-fill"), ("vm-095", "/")):
    for name, args in (("host.load", {}), ("host.io", {}), ("host.top_cpu", {"n": 3}), ("host.top_memory", {"n": 3}),
                       ("host.socket_summary", {}), ("host.directory_sizes", {"mount": mount}),
                       ("host.kernel_oom_records", {"minutes": 60})):
        spec = specs[name]
        o = d.call(spec, spec.args_model.model_validate(args), TargetRef.parse(f"{host}/host:{host}"))
        text = o.model_text if name not in ("host.top_cpu", "host.top_memory") else \
            f"{o.model_text.count('pid ')} processes, {o.model_text.count('(container ')} in containers"
        print(host, spec.model_name, "level", spec.level, o.status, "|", text[:240])
PY
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; agent, worker, scheduler on the same image; no startup errors; 14 lines "level 2 ok" with values (process names not printed); NO INTERFERENCE.

# --- S3.4 [VM vm-166 · bash] then [VM vm-095 · bash]: the probe with the shared walk budget (MUTATES) -------------
# Why: S3.3 showed `/` on vm-095 measured in name order: usr/ took the whole budget, var/ was never read. The fix is
#      in the probe only (services/target/service.py): checkout + target services rebuilt; the agent is unchanged.
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
H=$(hostname | sed 's/^argus-//'); case $H in vm095) V=vm-095; O=compose.core-join.yml; P=/;; *) V=vm-166; O=compose.loopback.yml; P=/srv/argus-lab-fill;; esac
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0019-batch2-host-probe --as $ME | tail -1
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file $V.env -f compose.target.yml -f $O up -d --build 2>&1 | grep -c Started | sed 's/^/target services started: /'; cd ~
sleep 10
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py 2>/dev/null | grep -E "directory|checks passed|FAIL" || echo "(phase3_check runs on vm-095 only)"
sudo docker exec argus-v18-host-probe python -c "
import json, urllib.request
tok = open('/run/argus-v18/host_probe_token').read().strip()
r = urllib.request.Request('http://127.0.0.1:8700/directory_sizes?path=$P', headers={'Authorization': 'Bearer ' + tok})
d = json.loads(urllib.request.urlopen(r, timeout=15).read())
print('$V', '$P', 'children', d['children_read'], 'entries', d['entries_read'], 'complete', d['complete'], [(c['name'], c['mib'], c['complete']) for c in d['children']][:10])"
echo "probe: $(sudo docker inspect -f 'restarts={{.RestartCount}} status={{.State.Status}}' argus-v18-host-probe)"
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^ref=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; DEPLOY OK; target services started; on vm-095 phase3_check N/N; `/` lists var/ (partial is
#           fine); restarts=0; LAB BASELINE OK; NO INTERFERENCE.

# =====================================================================================
# T-0019 batch 2, step 03 (cont.) — the model on the 55 evaluation cases with the new tools            [~30 min]
# Why: the new tools are offered to cpu_saturation, disk_pressure and container_restart_loop, and container.status
#      now shows id= (46 of 55 cases carry one): show the classes did not get worse. Measured on what main will be
#      after both PRs: a LOCAL merge of task/EVAL-2-model-trials (048a751) and this branch (b4623dc), commit 59defdf,
#      not pushed; exported with `git archive` from the laptop. The running agent is not touched (one-off containers,
#      eval-run.sh). Compare with EVAL-2's E.3c (1 trial, 53/55, 0.95) and E.4 (5 trials, 0.93, core 0.95).
# MUTATES: creates /opt/argus-v18/eval-src and the image argus-v18-eval:t0019b2; a results file. Both removed at the
#          end (the image by name only: no prune).
# =====================================================================================

# --- E.5 [LAPTOP · bash] export the merge to vm-095 ---------------------------------------------------------------
ssh argus-vm095 'grep -q "^holder=conantkd " /opt/argus-v18/SESSION && sudo rm -rf /opt/argus-v18/eval-src && sudo mkdir -p /opt/argus-v18/eval-src && echo ready'
git -C <scratchpad>/evalmerge archive 59defdf | ssh argus-vm095 'sudo tar -x -C /opt/argus-v18/eval-src && echo "exported $(sudo find /opt/argus-v18/eval-src -type f | wc -l) files"'

# --- E.6 [VM vm-095 · bash] build the eval image, 3 trials per case ---------------------------------------------
grep -q '^holder=conantkd ' /opt/argus-v18/SESSION || { echo "NOT YOUR SESSION"; exit 1; }
sudo docker build -q -t argus-v18-eval:t0019b2 /opt/argus-v18/eval-src | cut -c1-19
sudo git -C /opt/argus-v18/app -c safe.directory=/opt/argus-v18/app rev-parse --short HEAD    # the checkout: b4623dc
EV="ARGUS_EVAL_IMAGE=argus-v18-eval:t0019b2 ARGUS_EVAL_CASES=/opt/argus-v18/eval-src/tests/eval ARGUS_EVAL_CONFIG=/opt/argus-v18/eval-src/config"
sudo env $EV bash /opt/argus-v18/eval-src/ops/eval-run.sh --as conantkd --trials 3 2>&1 | tail -16
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expect: image built; per-class table, hard 0 0 0; NO INTERFERENCE.

# --- E.7 [LAPTOP · bash] + [VM vm-095 · bash]: E.5 and E.6 again, on the cases that answer the new routes ----------
# Why: E.6 showed the model asking get_directory_sizes 41 times in 24 disk runs, answered "unknown" by the cases'
#      "*" row; disk-filler-no-logs concluded 2 of 3 (EVAL-2: 1 of 5). 21 cases now answer the new routes from their
#      own story (61e11f1). Same blocks, with the local merge e9f048c (EVAL-2 048a751 + this branch 61e11f1, not
#      pushed); the old export and image removed first (`docker image rm argus-v18-eval:t0019b2`, by name).
# Then clean up: sudo rm -rf /opt/argus-v18/eval-src; sudo docker image rm argus-v18-eval:t0019b2 (by name, no prune)

# --- E.8 [LAPTOP · bash] + [VM vm-095 · bash]: E.5 and E.6 again, on this branch's head 040b827 -----------------------
# Why: E.7 (cases answering the new routes) brought abstention back (0.96) but disk_pressure fell to 0.79: with
#      "data-0007.bin 202 MiB" the model concluded in the abstain disk cases. The branch is now rebased on
#      task/EVAL-2-model-trials (its PR stacks on #89) and the system prompt says a large file shows where the space
#      went, not who wrote it. Export: `git archive HEAD` (040b827, pushed), same E.6 block (3 trials).
# --- E.9 [VM vm-095 · bash]: 2 more trials on the same image (E.6 with --trials 2, no rebuild): 5 trials in all,
#      as EVAL-2's E.4.

# --- S3.5 [VM vm-166 · bash] then [VM vm-095 · bash]: both VMs on the branch head 040b827 (MUTATES) -----------------
# Why: after the rebase the branch carries EVAL-2 (ACR-0008, its prompt rule, the fixtures) and the new prompt rule;
#      the VMs ran b4623dc. The target code is unchanged since b4623dc; the agent image changes (strategy, prompt).
#      On vm-095 agent, worker and scheduler are recreated together (S3.3's lesson). No model call.
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
H=$(hostname | sed 's/^argus-//'); case $H in vm095) V=vm-095; O=compose.core-join.yml;; *) V=vm-166; O=compose.loopback.yml;; esac
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0019-batch2-host-probe --as $ME | tail -1
cd /opt/argus-v18/app/deploy/target && sudo docker compose --env-file $V.env -f compose.target.yml -f $O up -d --build 2>&1 | grep -c -E "Started|Running" | sed 's/^/target services up: /'
if [ $V = vm-095 ]; then
  cd /opt/argus-v18/app/deploy/vm-095
  sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
  for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f '{{.Image}}' $c | cut -c8-19) $(sudo docker inspect -f '{{.State.Status}}' $c)"; done
  sudo docker logs --tail 5 argus-v18-worker 2>&1 | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
  sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py | grep -E "checks passed|FAIL"
  sudo docker exec -u 10011 argus-v18-worker python -c "
from argus.tooling.model_harness import SYSTEM_PROMPT
from argus.domain.model import TargetRef
from argus.infrastructure.wiring import Settings, tools_dispatcher
specs, d, _ = tools_dispatcher(Settings())
print('prompt rule present:', 'where the space went' in ' '.join(SYSTEM_PROMPT.split()))
for name, host, args in (('host.load', 'vm-166', {}), ('host.kernel_oom_records', 'vm-166', {'minutes': 120}), ('host.directory_sizes', 'vm-095', {'mount': '/'})):
    s = next(x for x in specs if x.name == name)
    o = d.call(s, s.args_model.model_validate(args), TargetRef.parse(f'{host}/host:{host}'))
    print(host, s.model_name, o.status, '|', o.model_text[:160])"
fi
cd ~
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; DEPLOY OK 040b827; target services up; vm-095: agent, worker, scheduler on one image, health
#           200, no startup errors, phase3_check N/N, prompt rule present, three reads ok; LAB BASELINE OK;
#           NO INTERFERENCE on both.
