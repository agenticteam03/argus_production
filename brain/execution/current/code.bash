# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# DEPLOY-B7-B8 (prepared 2026-10-20; run AFTER #188 merges) — both VMs to main <MAIN>: T-0045 B7 (#188: baseline,
#   6h/24h ranges, deploy events, migration 008) and B8 (#192: finer link reasons)                       [~30 min]
# What changes:
#   vm-095: migration 008 (deploy_event), then the agent image (agent, worker, scheduler) and the target services
#     (B8's exporter); the deploy event is recorded after the rebuild (the old image has no `argus deploy record`).
#   vm-166: the target services (B8's exporter: argus_probe_error). No database there.
# MUTATES: both VMs. Both leases.
# ROLLBACK: deploy.sh 2c7248b --as conantkd on each VM, then the compose commands below. Migration 008 stays (the old
#   image does not read deploy_event).
# Before running: replace <MAIN> with main's short commit after the merge (git log -1 --format=%h origin/main).
# =====================================================================================

# --- D.0 [LAPTOP · PowerShell] both leases, then each VM's session marker --------------------------------------------
python brain/tools/brain.py --as conantkd start --task DEPLOY-B7-B8 --vm both
#   [VM vm-095 · bash] and [VM vm-166 · bash]  echo 'holder=conantkd session=<id>' | sudo tee /opt/argus-v18/SESSION >/dev/null

# --- D.1 [VM vm-095 · bash] state probe, backup, deploy, migrate 008, rebuild (MUTATES) ------------------------------
ME=conantkd; BR=<MAIN>
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
free -m | awk '/Mem/{print "mem available " $7 " MiB"}'
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -2
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "applied|REFUSED|schema:"
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
cd /opt/argus-v18/app/deploy/target
sudo docker compose --env-file vm-095.env -f compose.target.yml -f compose.core-join.yml up -d --build </dev/null 2>&1 | grep -E "Recreated|rror" | tr '\n' ' '; echo
cd ~
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
SHA=$(sudo sed -n 's/^commit=//p' /opt/argus-v18/DEPLOYED)
sudo docker exec argus-v18-agent argus deploy record --commit "$SHA" --ref main --as $ME </dev/null | tail -1
# Expected: SESSION OK; ref=2c7248b, LAB BASELINE OK; NO INTERFERENCE; BACKUP OK; "deploy event NOT recorded here"
#   (the old image) then DEPLOY OK: <MAIN>; **+ 008_deploy_event applied**, schema 001 to 008; three "Recreated";
#   target services Recreated; health 200; the deploy event recorded.

# --- D.2 [VM vm-166 · bash] the target services (B8's exporter) (MUTATES) -------------------------------------------
ME=conantkd; BR=<MAIN>
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
cd /opt/argus-v18/app/deploy/target
sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml up -d --build </dev/null 2>&1 | grep -E "Recreated|rror" | tr '\n' ' '; echo
cd ~; sleep 30
sudo docker exec argus-v18-exporter grep -c failure_kind /app/service.py 2>/dev/null || echo "failure_kind not in the image"
for q in 'argus_probe_success{owner="argus-lab-api"}' 'count(argus_probe_error) or vector(0)'; do
  curl -s --data-urlencode "query=$q" http://127.0.0.1:18090/api/v1/query </dev/null | python3 -c 'import json,sys; r=json.load(sys.stdin)["data"]["result"]; print(sys.argv[1], "=", r[0]["value"][1] if r else "none")' "$q"
done
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: SESSION OK; NO INTERFERENCE; DEPLOY OK: <MAIN>; target services Recreated; failure_kind >= 1;
#   argus-lab-api probe = 1; count(argus_probe_error) = 0 (no probe failing in the idle lab); commit=<MAIN>,
#   LAB BASELINE OK; NO INTERFERENCE.

# --- D.3 [VM vm-095 · bash] verification (read-only) ------------------------------------------------------------------
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f "{{.Image}}" $c </dev/null | cut -c8-19) $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
sudo docker logs --tail 8 argus-v18-agent 2>&1 </dev/null | grep -i -E "startup validation|threshold|error" || echo "agent: no startup errors"
sudo docker logs --tail 8 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
sudo docker exec argus-v18-exporter grep -c failure_kind /app/service.py 2>/dev/null || echo "failure_kind not in the image"
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: the three on ONE image, restarts=0; no startup errors; db check passes (with B7's deploy_event checks);
#   failure_kind >= 1; 55/55; WRITE GATE CLOSED; commit=<MAIN> LAB BASELINE OK; NO INTERFERENCE.

# --- D.4 [VM vm-095 · bash, YOUR terminal] logged in: an incident's metrics show the long ranges, the baseline and the
#   deploy event (READ-ONLY). Asks your Argus user and password (hidden); prints names and counts, never the token.
python3 -c '
import getpass, json, ssl, urllib.parse, urllib.request
B = "https://127.0.0.1"; ctx = ssl._create_unverified_context()
user = input("Argus user: "); pw = getpass.getpass("Argus password: ")
body = urllib.parse.urlencode({"username": user, "password": pw, "scope": "read"}).encode()
tok = json.load(urllib.request.urlopen(urllib.request.Request(B + "/api/v1/auth/token", data=body), context=ctx))["access_token"]
def get(path):
    return json.load(urllib.request.urlopen(urllib.request.Request(B + path, headers={"Authorization": "Bearer " + tok}), context=ctx))
inc = get("/api/v1/incidents?limit=1")[0]
m = get("/api/v1/incidents/" + inc["id"] + "/metrics?range=24h")
print("ranges", m.get("ranges_available"), "baseline", [s["key"] for s in m["series"] if s.get("baseline")], "events", [e.get("kind") for e in m.get("events", [])])
'
# Expected: ranges include 6h and 24h; baseline on the series with enough data; a deploy event only when the incident's
#   window covers this deploy (an older incident shows none: not an error).

# --- D.5 [LAPTOP · PowerShell] release the leases ---------------------------------------------------------------------
python brain/tools/brain.py --as conantkd release
