# (archived) DEPLOY of #160/#161 (ACR-0017) to vm-095 (main 0b3b4e8), run 2026-10-16 by juanbetancurm;
#   leases vm-095 (session 19195da3fd04) and vm-166 (session bd7100416e18). Blocks as run, in order.
# =====================================================================================
# 2026-10-16 18:30-19:55 UTC, juanbetancurm. DEPLOY-161: vm-095 to main 0b3b4e8 (#160 + #161, ACR-0017: the incident
#   metrics and the system map for the UI). Same procedure as DEPLOY-151, with three corrections found on the way
#   (see evidence.md): both leases for an agent deploy, SC-01's leftover worker on vm-166, an empty marker on vm-095.
# What changed on vm-095: the agent image (two new GET routes; ARGUS_HOME_HOST=vm-095 on the agent) with the worker and
#   scheduler (one image; #152's tracing code arrives OFF); the config checkout (config/ui-incident-signals.yaml); the UI
#   image (the edge proxies the two new routes; the frontend unchanged). No migration.
# ROLLBACK (not needed): D.2 with main replaced by f9a4a0659f4e1f545d5fd4f4399992056314589f, then the two compose commands.
# =====================================================================================

# --- P.1 [VM vm-095 · bash, then VM vm-166 · bash] the state before (READ-ONLY, no lease needed) --------------------
# on vm-095:
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|^argus:|LAB BASELINE'
sudo git -C /opt/argus-v18/app -c safe.directory=/opt/argus-v18/app status --porcelain | wc -l
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler argus-v18-ui; do echo "$c $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c </dev/null)"; done
echo "health $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz </dev/null)"
sudo grep -c '^ARGUS_TRACING_ENABLED=1' /opt/argus-v18/hosts.env
cat /opt/argus-v18/SESSION
# on vm-166:
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E 'LAB BASELINE'
sudo docker ps -a --filter name=argus-lab-worker --filter name=argus-lab-client --filter name=argus-lab-backend --format '{{.Names}} {{.Status}}' </dev/null; echo "(nothing above: no scenario left over from the demo)"

# --- D.1 [LAPTOP · PowerShell] claim the vm-095 lease and write the session marker ----------------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git rev-parse --show-toplevel
Copy-Item brain\execution\current\code.bash ..\code.bash.deploy -Force
git checkout -- brain/execution/current/code.bash
git pull --ff-only
python brain/tools/brain.py --as juanbetancurm start --task DEPLOY-161 --vm vm-095
Copy-Item ..\code.bash.deploy brain\execution\current\code.bash -Force
git fetch origin
$sid = (git show origin/session:session.json | ConvertFrom-Json).vms.'vm-095'.session_id
Write-Output ('session ' + $sid)
ssh argus-vm095 ('echo holder=juanbetancurm session=' + $sid + ' | sudo tee /opt/argus-v18/SESSION >/dev/null; cat /opt/argus-v18/SESSION')
# brain.py then said: an agent deploy needs BOTH leases (PARALLEL_LANES.md) -> S.1. The first D.2/D.3 attempts did not
#   run anything (the marker was not theirs); the blocks below replace them.

# --- S.1 [LAPTOP · PowerShell] claim vm-166 too, renew vm-095, write vm-166's marker, show both markers -------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git rev-parse --show-toplevel
Copy-Item brain\execution\current\code.bash ..\code.bash.deploy -Force
git checkout -- brain/execution/current/code.bash
python brain/tools/brain.py --as juanbetancurm start --task DEPLOY-161 --vm vm-166
python brain/tools/brain.py --as juanbetancurm renew --vm vm-095
Copy-Item ..\code.bash.deploy brain\execution\current\code.bash -Force
git fetch origin
$sid166 = (git show origin/session:session.json | ConvertFrom-Json).vms.'vm-166'.session_id
ssh argus-vm166 ('echo holder=juanbetancurm session=' + $sid166 + ' | sudo tee /opt/argus-v18/SESSION >/dev/null')
ssh argus-vm095 'hostname; cat /opt/argus-v18/SESSION; ls -l /opt/argus-v18/SESSION'
ssh argus-vm166 'hostname; cat /opt/argus-v18/SESSION; ls -l /opt/argus-v18/SESSION'
# Expected: "Lease CLAIMED by juanbetancurm on vm-166", "Lease renewed on vm-095"; then argus-vm095 with
#   holder=juanbetancurm session=19195da3fd04, and argus-vm166 with holder=juanbetancurm session=<the new id>; both files
#   readable (-rw-r--r--). If vm-166 is in use by someone, or a marker is not yours: STOP and paste it.

# --- S.2 [VM vm-166 · bash] remove SC-01's leftover worker (the catalogue's reset), then the baseline (MUTATES lab) ---
if grep -q "^holder=juanbetancurm " /opt/argus-v18/SESSION; then
  echo "SESSION OK"
  sudo docker inspect -f '{{.Name}} service={{index .Config.Labels "com.docker.compose.service"}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}' argus-lab-worker </dev/null
  cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom </dev/null 2>&1 | tail -2; cd ~
  sleep 5
  sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E 'LAB BASELINE'
  sudo docker ps -a --filter name=argus-lab-worker --format '{{.Names}} {{.Status}}' </dev/null; echo "(nothing above: the worker is gone)"
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
else
  echo "NOT YOUR SESSION - nothing was run"
fi
# Expected: SESSION OK; /argus-lab-worker service=argus-lab-worker-oom oom=true restarts=<many> (if the service is NOT
#   argus-lab-worker-oom: it was not SC-01, paste it); "Removed"; LAB BASELINE OK; nothing listed; NO INTERFERENCE.

# --- S.3 [LAPTOP · PowerShell] write vm-095's marker again and show it ------------------------------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
git rev-parse --show-toplevel
ssh argus-vm095 'echo holder=juanbetancurm session=19195da3fd04 | sudo tee /opt/argus-v18/SESSION >/dev/null; hostname; cat /opt/argus-v18/SESSION; ls -l /opt/argus-v18/SESSION'
# Expected: argus-vm095; holder=juanbetancurm session=19195da3fd04; -rw-r--r-- ... 42 ... /opt/argus-v18/SESSION.
#   Then D.2 in a vm-095 SSH window (an open window is fine: the file is read when the block runs).

# --- D.2 [VM vm-095 · bash] main, backup, agent + worker + scheduler (MUTATES) ---------------------------------------
if grep -q "^holder=juanbetancurm " /opt/argus-v18/SESSION; then
  echo "SESSION OK"
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as juanbetancurm </dev/null | tail -1
  sudo bash /opt/argus-v18/app/ops/deploy.sh main --as juanbetancurm </dev/null | tail -1
  sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "applied|REFUSED|schema:"
  cd /opt/argus-v18/app/deploy/vm-095
  sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
  cd ~
  for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f '{{.Image}}' $c </dev/null | cut -c8-19) $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c </dev/null)"; done
  sudo docker logs --tail 5 argus-v18-agent 2>&1 </dev/null | grep -i -E "startup validation|ARGUS_HOME_HOST|ui-incident-signals|error" || echo "agent: no startup errors"
  sudo docker logs --tail 5 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
  sudo docker exec argus-v18-agent printenv ARGUS_HOME_HOST </dev/null
  sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
  sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
  sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
else
  echo "NOT YOUR SESSION - nothing was run"
fi
# Expected: SESSION OK; NO INTERFERENCE; BACKUP OK; DEPLOY OK: 0b3b4e8... (main); no migration to apply; agent,
#   worker, scheduler on ONE image, running restarts=0; health 200; agent: no startup errors; worker: no startup
#   errors; vm-095; 55/55 checks passed; WRITE GATE CLOSED. Anything else: STOP (rollback above) and paste it.

# --- D.3 [VM vm-095 · bash] the UI image (public mode), the new routes through the edge, the map read (MUTATES) ------
if grep -q "^holder=juanbetancurm " /opt/argus-v18/SESSION; then
  echo "SESSION OK"
  cd /opt/argus-v18/app/deploy/ui
  sudo docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml up -d --build </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
  cd ~
  for i in $(seq 1 30); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-v18-ui </dev/null 2>/dev/null); [ "$s" = healthy ] && break; sleep 3; done
  echo "ui: $(sudo docker inspect -f '{{.State.Status}} health={{.State.Health.Status}} restarts={{.RestartCount}}' argus-v18-ui </dev/null) ports: $(sudo docker port argus-v18-ui </dev/null | tr '\n' ' ')"
  for p in /api/v1/topology /api/v1/incidents/inc_smoke/metrics /api/v1/targets /api/v1/me /docs; do echo "GET $p $(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1$p </dev/null)"; done
  sudo docker exec argus-v18-agent python -c 'import json, re; from argus.infrastructure.wiring import build; a = build(require_credentials=False, load_credentials=False); v = a.topology.view(); t = json.dumps(v); print("map nodes", len(v["nodes"]), "edges", len(v["edges"]), "status", sorted({n["status"] for n in v["nodes"]}), "argus host", [h["id"] for h in v["hosts"] if h["role"] == "argus"], "address in answer", bool(re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", t)))' </dev/null 2>&1 | tail -1
  sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
else
  echo "NOT YOUR SESSION - nothing was run"
fi
# Expected: ui running health=healthy restarts=0, ports 443 and 80 only; GET /api/v1/topology 401,
#   /api/v1/incidents/inc_smoke/metrics 401 (they exist and need a login; 404 would mean the old edge), /targets 401,
#   /me 401, /docs 404; map nodes = the inventory's targets, edges > 0, status running or unknown (unknown only where
#   a signal is missing), argus host ['vm-095'], address in answer False; commit=0b3b4e8... ref=main;
#   LAB BASELINE OK; NO INTERFERENCE.

# --- D.4 [VM vm-095 · bash, YOUR terminal] logged in, through the public edge, as the UI does (READ-ONLY) ------------
# Asks your Argus user and password (hidden; never paste them anywhere). Prints only counts and names, never the token.
python3 -c '
import getpass, json, re, ssl, urllib.parse, urllib.request
B = "https://127.0.0.1"; ctx = ssl._create_unverified_context()
user = input("Argus user: "); pw = getpass.getpass("Argus password: ")
body = urllib.parse.urlencode({"username": user, "password": pw, "scope": "read"}).encode()
tok = json.load(urllib.request.urlopen(urllib.request.Request(B + "/api/v1/auth/token", data=body), context=ctx))["access_token"]
def get(path):
    r = urllib.request.urlopen(urllib.request.Request(B + path, headers={"Authorization": "Bearer " + tok}), context=ctx)
    return r.status, json.load(r)
s, me = get("/api/v1/me"); print("me", s, me.get("role"))
s, incs = get("/api/v1/incidents?limit=30"); print("incidents", s, len(incs))
s, topo = get("/api/v1/topology"); print("topology", s, "nodes", len(topo["nodes"]), "edges", len(topo["edges"]))
leak = bool(re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", json.dumps(topo)))
inc = next((i for i in incs if i.get("root_cause_target")), incs[0] if incs else None)
if inc:
    s, m = get("/api/v1/incidents/" + inc["id"] + "/metrics?range=30m")
    print("metrics", s, inc["id"], inc.get("class"), "series", [x["key"] for x in m["series"]], "points", len(m["series"][0]["points"]) if m["series"] else 0)
    if me.get("role") in ("operator", "approver"):
        s, ov = get("/api/v1/topology?incident_id=" + inc["id"])
        print("overlay", s, [e["label"] for e in ov["edges"] if e["state"] == "broken"])
        leak = leak or bool(re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", json.dumps(ov)))
print("address in answers", leak)
'
# Expected: me 200 <your role>; incidents 200 <n>; topology 200 with nodes and edges; metrics 200 <an incident id>
#   <its class> with its series and about 60-130 points (null values are gaps, normal); for operator/approver,
#   overlay 200 (a list of broken links, possibly empty); address in answers False. Any 4xx/5xx: paste it.
# Then in the browser: log in to the UI and open the Incidents list and one incident. It must look and work as in the
#   demo (Map and Metrics tabs are still hidden: expected until Juan's build).

# --- D.5 [LAPTOP · PowerShell] release both leases -------------------------------------------------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\argus_production
python brain/tools/brain.py --as juanbetancurm release
# Expected: "Lease released on vm-095 and vm-166" (or two lines).
# VERDICT: DONE if S.2, D.2, D.3 and D.4 match. Then: a record PR of this deployment (agent prepares it), and Juan
#   starts the frontend work (VITE_ARGUS_INSIGHTS=1, the Map and Metrics tabs, the contract tests).

