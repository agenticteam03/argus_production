# (archived) DEPLOY-195 step 01, run 2026-10-20 05:20-05:30 UTC by conantkd's agent over ssh (conantkd away, authorized);
#   leases vm-095 + vm-166, session ad0eb3554825. Ran as written (D.0 to D.3). See evidence.md.
# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# DEPLOY-195 — both VMs to main bdcd048: T-0045 B8 (#192: finer link reasons) and the redaction fix (#195: a token glued
#   to a non-ASCII letter is masked)                                                                      [~20 min]
# What changes:
#   vm-095: the agent image (agent, worker, scheduler: B8's adapter and topology, the redaction) and the target services
#     (B8's exporter). No migration (008 comes with B7, #188, in review).
#   vm-166: the target services (B8's exporter: argus_probe_error).
# MUTATES: both VMs. Both leases. Run by conantkd's agent over ssh (conantkd away, authorized).
# ROLLBACK: deploy.sh 2c7248b --as conantkd on each VM, then the compose commands below.
# =====================================================================================

# --- D.0 [LAPTOP] both leases, then each VM's session marker ----------------------------------------------------------
python brain/tools/brain.py --as conantkd start --task DEPLOY-195 --vm both
#   [VM vm-095 · bash] and [VM vm-166 · bash]  echo 'holder=conantkd session=<id>' | sudo tee /opt/argus-v18/SESSION >/dev/null

# --- D.1 [VM vm-095 · bash] state probe, backup, deploy, rebuild (MUTATES) --------------------------------------------
ME=conantkd; BR=bdcd048
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
free -m | awk '/Mem/{print "mem available " $7 " MiB"}'
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "applied|REFUSED|schema:" | tail -1
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|rror"
cd /opt/argus-v18/app/deploy/target
sudo docker compose --env-file vm-095.env -f compose.target.yml -f compose.core-join.yml up -d --build </dev/null 2>&1 | grep -E "Recreated|rror" | tr '\n' ' '; echo
cd ~
# Expected: SESSION OK; ref=2c7248b, LAB BASELINE OK; NO INTERFERENCE; BACKUP OK; DEPLOY OK: bdcd048; schema 001 to 007
#   (nothing new); three "Recreated"; target services Recreated.

# --- D.2 [VM vm-166 · bash] the target services (B8's exporter) (MUTATES) -------------------------------------------
ME=conantkd; BR=bdcd048
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
cd /opt/argus-v18/app/deploy/target
sudo docker compose --env-file vm-166.env -f compose.target.yml -f compose.loopback.yml up -d --build </dev/null 2>&1 | grep -E "Recreated|rror" | tr '\n' ' '; echo
cd ~; sleep 45
echo "failure_kind in exporter image: $(sudo docker exec argus-v18-exporter grep -c failure_kind /app/service.py </dev/null 2>/dev/null)"
for q in 'argus_probe_success{owner="argus-lab-api"}' 'count(argus_probe_error) or vector(0)'; do
  curl -s --data-urlencode "query=$q" http://127.0.0.1:18090/api/v1/query </dev/null | python3 -c 'import json,sys; r=json.load(sys.stdin)["data"]["result"]; print(sys.argv[1], "=", r[0]["value"][1] if r else "none")' "$q"
done
sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E '^argus-v18-' | sort | tr '\n' ';'; echo
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: SESSION OK; LAB BASELINE OK; NO INTERFERENCE; DEPLOY OK: bdcd048; target services Recreated; failure_kind
#   >= 1; argus-lab-api probe = 1 (or none if SC-03's api is not running); count(argus_probe_error) = 0 (no probe
#   failing in the idle lab); every argus-v18-* Up; commit=bdcd048, LAB BASELINE OK; NO INTERFERENCE.

# --- D.3 [VM vm-095 · bash] verification (read-only) ------------------------------------------------------------------
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f "{{.Image}}" $c </dev/null | cut -c8-19) $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
sudo docker logs --tail 8 argus-v18-agent 2>&1 </dev/null | grep -i -E "startup validation|threshold|error" || echo "agent: no startup errors"
sudo docker logs --tail 8 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
sudo docker exec argus-v18-worker python -c "from argus.capabilities.redaction import Redactor; t='Ab3'*14; print('redaction glued token masked:', t not in Redactor().text('é'+t)[0])" </dev/null
sudo docker exec argus-v18-agent python -c "from argus.application.topology import LINK_REASONS; from argus.ports.ports import ProbeSample; print('B8 reasons', sorted(LINK_REASONS.values()), 'error_kind' in ProbeSample._fields)" </dev/null
sudo docker exec argus-v18-agent python -c 'import json, re; from argus.infrastructure.wiring import build; a = build(require_credentials=False, load_credentials=False); v = a.topology.view(); print("map nodes", len(v["nodes"]), "edges", len(v["edges"]), "states", sorted({e["state"] for e in v["edges"]}), "reasons", sorted({e["reason"] for e in v["edges"] if e.get("reason")}), "address", bool(re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", json.dumps(v))))' </dev/null 2>&1 | tail -1
for p in /api/v1/topology /api/v1/overview /api/v1/me /docs; do echo "GET $p $(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1$p </dev/null)"; done
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
free -m | awk '/Mem/{print "mem available " $7 " MiB"}'
# Expected: health 200; the three on ONE image, restarts=0; no startup errors; 23/23; redaction glued token masked:
#   True; B8 reasons listed, True; map nodes > 0, edges > 0, address False; /api/v1 routes 401, /docs 404; 55/55; WRITE
#   GATE CLOSED; commit=bdcd048 LAB BASELINE OK; NO INTERFERENCE.

# --- D.4 [LAPTOP] release the leases ----------------------------------------------------------------------------------
python brain/tools/brain.py --as conantkd release
