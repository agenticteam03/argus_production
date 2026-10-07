# (archived) T-0019 batch 1 step 03, run 2026-10-07 by the agent over SSH (session 3307114120d3)
# =====================================================================================
# T-0019 batch 1, step 03 — secrets, argus-lab-db, db-probe on vm-166; agent on vm-095; verify       [~15 min]
# Why: the probe needs its token and the monitoring role's password; the lab database (TESTING ONLY) gives it a
#      healthy reference; the agent needs the same token for vm-166/db_probe or it refuses to start.
# MUTATES: vm-166: checkout, 3 secret files (generated there, never printed, kept on re-run), argus-lab-db created
#          (base-166), the 4 target services rebuilt + argus-v18-db-probe created. vm-095: checkout, the agent's
#          copy of the token, argus-v18-agent rebuilt (also brings a90400e). No other lab container changes.
# Undo: vm-166: docker rm -f argus-v18-db-probe argus-lab-db; deploy.sh main + the target `up -d --build`;
#       the secret files may stay (unused). vm-095: deploy.sh main + the agent rebuild (main has no db_probe
#       executor, so the extra token file is simply unused).
# Lease: conantkd (session 3307114120d3).
# =====================================================================================

# --- S3.1 [VM vm-166 · bash] (ssh argus-vm166) secrets + lab DB + target services (MUTATES) ------------------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
echo "tunnel key permits 18704: $(sudo grep -c 'permitopen="127.0.0.1:18704"' /var/lib/argus-v18-tunnel/.ssh/authorized_keys)"
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0019-db-probe --as $ME | tail -3
sudo sh -c 'umask 077; S=/opt/argus-v18/secrets; mkdir -p $S/lab-db
  for f in $S/db_probe_token $S/lab-db/postgres_password $S/lab-db/monitor_password; do
    [ -s $f ] || python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $f; done
  chown 70:70 $S/lab-db/postgres_password $S/lab-db/monitor_password; chmod 400 $S/lab-db/*; chmod 600 $S/db_probe_token
  stat -c "%a %u:%g %n" $S/db_probe_token $S/lab-db/postgres_password $S/lab-db/monitor_password'
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile base-166 up -d argus-lab-db 2>&1 | tail -3; cd ~
for i in $(seq 1 24); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-lab-db 2>/dev/null); echo "lab-db health=$s"; [ "$s" = healthy ] && break; sleep 5; done
sudo docker exec argus-lab-db psql -U postgres -d argus_lab -Atc "SELECT rolname, rolsuper, pg_has_role(rolname, 'pg_monitor', 'member'), rolconnlimit FROM pg_roles WHERE rolname = 'argus_monitor'"
sudo docker exec argus-lab-db psql -U postgres -d argus_lab -Atc "SHOW max_connections"
cd /opt/argus-v18/app/deploy/target
echo "services: $(sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml config --services | sort | tr '\n' ' ')"
sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml up -d --build 2>&1 | tail -8; cd ~
sleep 20
sudo docker ps --format '{{.Names}}\t{{.Status}}' | grep -E '^argus-(v18|lab)-' | sort
echo "loopback 18704 healthz: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18704/healthz)"
sudo docker exec -i argus-v18-db-probe python - <<'PY'
import json, urllib.error, urllib.request
tok = open("/run/argus-v18/db_probe_token").read().strip()
def get(q):
    r = urllib.request.Request("http://127.0.0.1:8700/database/health?" + q, headers={"Authorization": "Bearer " + tok})
    try:
        with urllib.request.urlopen(r, timeout=10) as x:
            return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
c, d = get("name=argus-lab-db")
print("health", c, {k: d.get(k) for k in ("ok", "max_connections", "reserved_connections", "usable_connections",
      "client_connections", "usage_percent", "by_state", "lock_waits", "blocked_sessions")})
print("sql text in answer:", "query" in json.dumps(d))
print("not allowlisted:", get("name=postgres")[0])
PY
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; tunnel key permits 18704: 1; DEPLOY OK (task/T-0019-db-probe); 3 secret files 400/600
#           (lab-db 70:70); lab-db health=healthy; argus_monitor|f|t|3; max_connections 20; services list includes
#           argus-v18-db-probe; all target services Up; healthz 200; health 200 ok=True max=20 reserved=3 usable=17;
#           sql text in answer: False; not allowlisted: 400; LAB BASELINE OK (argus-lab-db included); NO INTERFERENCE.

# --- S3.2 [LAPTOP · bash] the agent's copy of the token: vm-166 -> vm-095 through a pipe (never printed or stored) --
ssh argus-vm166 'sudo cat /opt/argus-v18/secrets/db_probe_token' | ssh argus-vm095 'sudo sh -c "umask 077; f=/opt/argus-v18/secrets/agent/vm-166/db_probe_token; cat > \$f; chown 10010:10010 \$f; chmod 400 \$f; stat -c \"%a %u:%g %n\" \$f"'
a=$(ssh argus-vm166 'sudo sha256sum /opt/argus-v18/secrets/db_probe_token' | cut -c1-64)
b=$(ssh argus-vm095 'sudo sha256sum /opt/argus-v18/secrets/agent/vm-166/db_probe_token' | cut -c1-64)
[ -n "$a" ] && [ "$a" = "$b" ] && echo "TOKEN COPY MATCH" || echo "TOKEN COPY MISMATCH - stop"
# Expected: 400 10010:10010 …/vm-166/db_probe_token; TOKEN COPY MATCH (only the comparison is printed).

# --- S3.3 [VM vm-095 · bash] (ssh argus-vm095) checkout + agent rebuild + checks (MUTATES; no model call) ----------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh task/T-0019-db-probe --as $ME | tail -3
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent 2>&1 | tail -4; cd ~
for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz); echo "health $c"; [ "$c" = 200 ] && break; sleep 5; done
sudo docker logs --tail 5 argus-v18-agent 2>&1 | grep -i -E "startup validation|missing credential|error" || echo "no startup errors"
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py | grep -E "db probe|checks passed|FAIL"
sudo docker exec -i argus-v18-agent python - <<'PY'
# the agent's own code path for database.health: capability + executor + token + tunnel + redaction (no incident)
from argus.adapters.outbound.config_adapters import YamlInventory
from argus.capabilities.catalog import NoArgs, build_catalog
from argus.capabilities.redaction import Redactor
from argus.domain.model import TargetRef
from argus.infrastructure.wiring import Settings
from argus.tooling.dispatch import Dispatcher
from argus.tooling.executors import ExecutorRegistry, TargetAgentClient
s = Settings()
inv = YamlInventory((s.config_dir / "inventory.yaml").read_text(encoding="utf-8"))
reg = ExecutorRegistry()
reg.register("db_probe", lambda url, tok: TargetAgentClient(url, tok))
spec = next(x for x in build_catalog() if x.name == "database.health")
o = Dispatcher(inv, reg, {("vm-166", "db_probe"): s.secret("vm-166/db_probe_token")}, Redactor()).call(
    spec, NoArgs(), TargetRef.parse("vm-166/container:argus-lab-db"))
print("capability", spec.model_name, "level", spec.level, "status", o.status)
print(o.model_text)
PY
sudo bash /opt/argus-v18/app/ops/deploy.sh status | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
# Expected: SESSION OK; DEPLOY OK (task/T-0019-db-probe); agent recreated; health 200; no startup errors;
#           phase3_check: the 5 "db probe" checks PASS and "N/N checks passed"; capability inspect_database_health
#           level 3 status ok, text "database argus-lab-db (argus_lab): x/17 client connections ..."; LAB BASELINE OK;
#           NO INTERFERENCE.
