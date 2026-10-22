# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# PHASE-16 step 2 (prepared 2026-10-21, run after this PR and #240 merge) — EdDSA switched on in the lab: the Ed25519
#   key generated on vm-095 (never printed), the agent recreated with its mount; the first `prune-sessions` dry run.
#   [~25 min]
# MUTATES: vm-095 (backup, checkout, one new secret file, agent and worker containers). Both leases. vm-166: no change.
# EFFECT: every open session must log in again (an HS256 token is refused once the key is mounted).
# ROLLBACK: remove the jwt_ed25519_key line from compose.core.yml (or deploy.sh <previous main>), then the compose
#   command of D.2; the key file may stay (only the agent signs, and only when it is mounted).
# =====================================================================================

# --- D.0 [LAPTOP · PowerShell] both leases, markers, then [VM vm-166 · bash] before -----------------------------------
python brain/tools/brain.py --as conantkd start --task PHASE-16-step-2 --vm both
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1

# --- D.1 [VM vm-095 · bash] probe, backup, deploy main, then the key BEFORE any `up` (MUTATES) ------------------------
ME=conantkd; BR=<main after the merge>
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -3
S=/opt/argus-v18/secrets/agent; K=$S/jwt_ed25519_key
# a missing bind source becomes a directory: create the file first, owned and moded like jwt_signing_key; never printed
if sudo test -e "$K"; then echo "key exists, kept"; else
  sudo sh -c "umask 077; openssl genpkey -algorithm ed25519 -out '$K'" </dev/null
  sudo chown --reference="$S/jwt_signing_key" "$K"; sudo chmod --reference="$S/jwt_signing_key" "$K"; fi
sudo test -f "$K" && echo "key file: $(sudo stat -c '%U:%G %a' "$K") vs $(sudo stat -c '%U:%G %a' "$S/jwt_signing_key")"
sudo openssl pkey -in "$K" -pubout </dev/null | openssl pkey -pubin -noout -text | head -1   # "ED25519 Public-Key:"

# --- D.2 [VM vm-095 · bash] recreate the agent and the worker (MUTATES) -------------------------------------------------
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
cd ~
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"

# --- D.3 [VM vm-095 · bash] verification (read-only) --------------------------------------------------------------------
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do n=$(sudo docker logs --since 10m $c 2>&1 </dev/null | grep -ciE "traceback|error"); echo "$c error lines: $n"; done
sudo docker exec argus-v18-agent test -f /run/argus-secrets/jwt_ed25519_key </dev/null && echo "mount is a file"
sudo docker exec argus-v18-agent python -c "from argus.infrastructure.wiring import Settings, ed25519_signing_key as k; print('EdDSA on' if k(Settings().secret('jwt_ed25519_key')) else 'EdDSA OFF')" </dev/null
echo "/me without a token: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/api/v1/me </dev/null) (401)"
sudo docker exec argus-v18-agent argus db check </dev/null | grep -E "FAIL|checks passed"
sudo docker exec argus-v18-agent argus audit verify </dev/null | tail -1
# the first session-retention dry run, as the owner (like ops/checkpoint-retention.sh), read-only
OWNER=$(sudo stat -c %u:%g /opt/argus-v18/secrets/postgres/owner_password)
sudo docker run --rm --network argus-v18-core --user "$OWNER" --read-only --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 64 --memory 128m --mount "type=bind,source=/opt/argus-v18/secrets/postgres/owner_password,target=/run/argus-secrets/db_password,readonly" \
  -e ARGUS_DB_BACKEND=postgres -e ARGUS_PG_USER=argus_owner argus-v18-agent:1 python -m argus db prune-sessions </dev/null
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1

# --- D.4 [LAPTOP · PowerShell, conantkd's terminal] log in on the UI again: a new EdDSA token; the old one is 401 -------

# --- D.5 [VM vm-166 · bash] after, then [LAPTOP] release ----------------------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
python brain/tools/brain.py --as conantkd release
