# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# PHASE-16 step 1 deploy (PREPARED 2026-10-21; run AFTER #223 merges) — vm-095 to main <MAIN>: sessions, revocation,
#   the persisted login limiter, permissions, the audit hash chain (ACR-0018). Migrations 010 and 011.     [~25 min]
# What changes:
#   vm-095: migrations 010 (auth_session, login_failure) and 011 (audit seq, prev_hash, hash), then the agent image
#     (agent, worker, scheduler). Every open session must log in once (old tokens have no session row).
#   EdDSA stays OFF here: no jwt_ed25519_key is installed (step 2 switches it on, with the compose mount).
#   vm-166: no change (its lease is held because the agent changes).
# MUTATES: vm-095. Both leases.
# ROLLBACK: deploy.sh <PREVIOUS> --as conantkd, then the compose command of D.1. Migrations 010 and 011 stay: the old
#   image ignores auth_session / login_failure, and writes audit rows without a hash (verify then names them).
# =====================================================================================

# --- D.0 [LAPTOP · PowerShell] both leases, then each VM's session marker --------------------------------------------
python brain/tools/brain.py --as conantkd start --task PHASE-16-step-1-deploy --vm both
#   [VM vm-095 · bash] and [VM vm-166 · bash]  echo 'holder=conantkd session=<id>' | sudo tee /opt/argus-v18/SESSION >/dev/null

# --- D.0b [VM vm-166 · bash] before (read-only) -----------------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1

# --- D.1 [VM vm-095 · bash] probe, backup, deploy, migrate 010 and 011, rebuild (MUTATES) -----------------------------
ME=conantkd; BR=<MAIN>
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -3
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "\+ |REFUSED|schema:"
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
# the edge's locations.conf changed (#223: logout is routed): rebuild the UI image, as in DEPLOY-189 D.2
cd /opt/argus-v18/app/deploy/ui
sudo docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml up -d --build </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 30); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-v18-ui </dev/null 2>/dev/null); [ "$s" = healthy ] && break; sleep 3; done; echo "ui health $s"
echo "logout without a token: $(curl -sk -o /dev/null -w '%{http_code}' -X POST https://127.0.0.1/api/v1/auth/logout </dev/null) (401 = routed)"
cd ~
cd ~
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
# Expected: SESSION OK; BACKUP OK; DEPLOY OK: <MAIN>; "+ 010_session_login applied", "+ 011_audit_chain applied",
#   schema 001 to 011; three "Recreated"; health 200.

# --- D.2 [VM vm-095 · bash] verification (read-only) ------------------------------------------------------------------
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f "{{.Image}}" $c </dev/null | cut -c8-19) $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
sudo docker exec argus-v18-agent argus db check </dev/null | grep -E "FAIL|checks passed"
sudo docker exec argus-v18-agent argus audit verify </dev/null | tail -2
sudo docker logs --since 5m argus-v18-scheduler 2>&1 </dev/null | grep -E "audit chain" | tail -2
for p in /api/v1/topology /api/v1/me /docs; do echo "GET $p $(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1$p </dev/null)"; done
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: one image, restarts=0; 35/35 database checks (010's six); "AUDIT CHAIN OK: N rows chained, M written before
#   the chain"; the scheduler's "security.audit_chain_verified"; 401/401/404; 55/55; WRITE GATE CLOSED; NO INTERFERENCE.

# --- D.3 [VM vm-095 · bash, YOUR terminal] log in, see /me's permissions, log out, see the token refused (READ-ONLY
#   apart from your own session row). Asks your Argus user and password (hidden); never prints the token.
python3 -c '
import getpass, json, ssl, urllib.parse, urllib.request, urllib.error
B = "https://127.0.0.1"; ctx = ssl._create_unverified_context()
user = input("Argus user: "); pw = getpass.getpass("Argus password: ")
body = urllib.parse.urlencode({"username": user, "password": pw, "scope": "read"}).encode()
tok = json.load(urllib.request.urlopen(urllib.request.Request(B + "/api/v1/auth/token", data=body), context=ctx))["access_token"]
h = {"Authorization": "Bearer " + tok}
me = json.load(urllib.request.urlopen(urllib.request.Request(B + "/api/v1/me", headers=h), context=ctx))
print("permissions", me.get("permissions"))
try:
    urllib.request.urlopen(urllib.request.Request(B + "/api/v1/auth/logout", data=b"", headers=h), context=ctx); print("logout ok")
except urllib.error.HTTPError as e:
    print("logout", e.code)
try:
    urllib.request.urlopen(urllib.request.Request(B + "/api/v1/me", headers=h), context=ctx); print("token still works: WRONG")
except urllib.error.HTTPError as e:
    print("after logout", e.code)
'
# Expected: permissions [...]; logout ok (the edge routes it, #223); after logout 401.

# --- D.4 [VM vm-166 · bash] after, then [LAPTOP] release ---------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
python brain/tools/brain.py --as conantkd release
