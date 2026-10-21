# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# DEPLOY-A4479DF (2026-10-21) — vm-095 to main a4479df: phase 16 step 1 (#223, migrations 010 and 011), ACR-0026
#   (#210), ACR-0028 (#222), #225, T-0046 L3 (#226, link_states off) and L4 (#227), T-0047 H1 (#228), React Router 7
#   (#229, UI image rebuilt). Run from PHASE-16/step-01/code.bash with BR=a4479df.                        [~45 min]
# MUTATES: vm-095 (backup, checkout, migrations 010 and 011, agent and UI images). Both leases. vm-166: no change.
# ROLLBACK: deploy.sh 024aa6f --as conantkd, then the compose commands of D.1. Migrations 010 and 011 stay (the old
#   image ignores auth_session / login_failure and writes audit rows without a hash; `argus audit verify` names them).
# =====================================================================================

# --- D.0 [LAPTOP · PowerShell] both leases, then each VM's session marker --------------------------------------------
python brain/tools/brain.py --as conantkd start --task DEPLOY-A4479DF --vm both
#   [VM vm-095 · bash] and [VM vm-166 · bash]  echo 'holder=conantkd session=<id>' | sudo tee /opt/argus-v18/SESSION >/dev/null

# --- D.0b [VM vm-166 · bash] before (read-only) -----------------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1

# --- D.1 [VM vm-095 · bash] probe, backup, deploy, migrate 010 and 011, rebuild agent and UI (MUTATES) ----------------
ME=conantkd; BR=a4479df
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
echo "mem available $(free -m | awk '/Mem:/{print $7}') MiB"
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -3
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "\+ |REFUSED|schema:"
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
cd /opt/argus-v18/app/deploy/ui
sudo docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml up -d --build </dev/null 2>&1 | grep -E "Recreated|Started|rror" | tr '\n' ' '; echo
for i in $(seq 1 30); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-v18-ui </dev/null 2>/dev/null); [ "$s" = healthy ] && break; sleep 3; done; echo "ui health $s"
cd ~
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
echo "logout without a token: $(curl -sk -o /dev/null -w '%{http_code}' -X POST https://127.0.0.1/api/v1/auth/logout </dev/null) (401 = routed)"

# --- D.2 [VM vm-095 · bash] verification (read-only) ------------------------------------------------------------------
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f "{{.Image}}" $c </dev/null | cut -c8-19) $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do n=$(sudo docker logs --since 10m $c 2>&1 </dev/null | grep -ciE "traceback|error"); echo "$c error lines: $n"; done
sudo docker exec argus-v18-agent argus db check </dev/null | grep -E "FAIL|checks passed"
sudo docker exec argus-v18-agent argus audit verify </dev/null | tail -2
sudo docker logs --since 10m argus-v18-scheduler 2>&1 </dev/null | grep -E "audit chain|link states|reconcile firing alerts: " | tail -4
for p in /api/v1/topology /api/v1/me /docs; do echo "GET $p $(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1$p </dev/null)"; done
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1

# --- D.2b [VM vm-095 · bash] ACR-0028 live: each READ_ONLY_SENSITIVE read once on the lab through the worker's own
#   catalogue (the MCP tools process as argus-tools, §12.6), status / kept keys / dropped names only; nothing stored.
#   The script below is copied to /tmp, run with `docker exec argus-v18-worker python`, then removed from both.
: <<'PY'
# ACR-0028 live check: every READ_ONLY_SENSITIVE read once on the lab, through the real Dispatcher. Prints status,
# how many value keys were kept and the names minimization dropped. Never prints a value; stores nothing.
from argus.domain.model import TargetRef
from argus.infrastructure.wiring import build
app = build()
specs, disp = app.catalogue.list(), app.catalogue
TARGETS = {"container": TargetRef.parse("vm-166/container:argus-lab-api"), "host": TargetRef.parse("vm-166/host:vm-166")}
EXTRA = {"container.search_logs": {"pattern": "error"}}
for s in sorted((x for x in specs if x.safety_class == "READ_ONLY_SENSITIVE"), key=lambda x: x.name):
    kind = "container" if "container" in s.target_kinds else "host"
    try:
        args = s.args_model(**EXTRA.get(s.name, {}))
    except Exception as e:
        print(f"{s.name:32} SKIPPED (needs arguments: {sorted(k for k, f in s.args_model.model_fields.items() if f.is_required())})")
        continue
    if s.runs_in == "worker" or s.max_subcalls:
        print(f"{s.name:32} SKIPPED (in-worker or combined)"); continue
    o = disp.call(s, args, TARGETS[kind])
    kept = len(o.values) if isinstance(o.values, dict) else 0
    print(f"{s.name:32} {o.status:8} {o.error_category or '':12} kept_keys={kept:2} dropped={o.dropped_fields}")
PY

# --- D.4 [VM vm-166 · bash] after, then [LAPTOP] release ---------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
python brain/tools/brain.py --as conantkd release
