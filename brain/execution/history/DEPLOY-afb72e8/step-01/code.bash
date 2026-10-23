# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# DEPLOY-afb72e8 (prepared 2026-10-22 by the agent; to be run by conantkd) — main afb72e8 on vm-095. Since 6c83da3:
#   phase 16 step 2 (EdDSA: the Ed25519 key generated on vm-095, never printed, and mounted), `db prune-sessions`
#   (#240), T-0047 H4/H5 (H5 offered to no class), and the UI with Vite 8 and the contrast fix (#242, #257).
#   No new migration (the database stays at 012). vm-166: no change (nothing under services/ or deploy/target/).
#   [~35 min]
# MUTATES: vm-095 (backup, checkout, one new secret file, agent/worker/scheduler and the UI). Both leases.
# EFFECT: every open session must log in again (an HS256 token is refused once the key is mounted).
# ROLLBACK: sudo bash /opt/argus-v18/app/ops/deploy.sh 6c83da3 --as conantkd, then the compose commands of D.2 and D.3
#   (the key file may stay: the 6c83da3 compose does not mount it).
# =====================================================================================

# --- D.0 [LAPTOP · PowerShell] both leases ----------------------------------------------------------------------------
python brain/tools/brain.py --as conantkd start --task DEPLOY-afb72e8 --vm both
# Expected: "Lease CLAIMED by conantkd on vm-095 and vm-166"; copy the two SESSION lines it prints into D.1 / D.5.

# --- D.1 [VM vm-166 · bash] (ssh argus-vm166) marker, before --------------------------------------------------------------
echo 'holder=conantkd session=<from D.0>' | sudo tee /opt/argus-v18/SESSION >/dev/null
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
# Expected: a "before" snapshot line.

# --- D.2 [VM vm-095 · bash] (ssh argus-vm095) marker, before, backup, checkout, the key BEFORE any `up` (MUTATES) ------
ME=conantkd; BR=afb72e8
echo 'holder=conantkd session=<from D.0>' | sudo tee /opt/argus-v18/SESSION >/dev/null
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || echo "NOT YOUR SESSION - stop here"
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
sudo openssl pkey -in "$K" -pubout </dev/null | openssl pkey -pubin -noout -text | head -1
# Expected: SESSION OK; ref=6c83da3, LAB BASELINE OK; a before snapshot; BACKUP OK; DEPLOY OK: afb72e8 (rebuild
#   hints: agent/worker/scheduler and UI; no migration); "key file: X:Y 600 vs X:Y 600" (same owner and mode);
#   "ED25519 Public-Key:". A directory at $K, or a different owner/mode: STOP (rollback above).

# --- D.3 [VM vm-095 · bash] the agent, worker and scheduler on one image, with the key mounted (MUTATES) ---------------
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
cd ~
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
sudo docker exec argus-v18-agent argus deploy record --commit afb72e8 --ref main --as $ME </dev/null | tail -1
# Expected: three Recreated/Started, no "rror"; health 200; the deploy event recorded.

# --- D.4 [VM vm-095 · bash] the UI (Vite 8, the contrast fix; Map and Metrics stay on) (MUTATES) ------------------------
cd /opt/argus-v18/app/deploy/ui
sudo docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml up -d --build </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
cd ~
for i in $(seq 1 30); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-v18-ui </dev/null 2>/dev/null); [ "$s" = healthy ] && break; sleep 3; done
echo "ui: $(sudo docker inspect -f '{{.State.Status}} health={{.State.Health.Status}} restarts={{.RestartCount}}' argus-v18-ui </dev/null) ports: $(sudo docker port argus-v18-ui </dev/null | tr '\n' ' ')"
echo "insights in bundle: $(sudo docker exec argus-v18-ui sh -c 'grep -l "api/v1/topology" /usr/share/nginx/html/assets/*.js | wc -l' </dev/null)"
echo "solid button colour in bundle: $(sudo docker exec argus-v18-ui sh -c 'grep -l "accent-solid" /usr/share/nginx/html/assets/*.css | wc -l' </dev/null)"
# Expected: ui Recreated/Started; healthy restarts=0; ports 443 and 80 only; insights >= 1; solid button colour >= 1.

# --- D.5 [VM vm-095 · bash] verification (read-only), the first `prune-sessions` dry run, after -----------------------
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c $(sudo docker inspect -f "{{.State.Status}} restarts={{.RestartCount}}" $c </dev/null)"; done
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do n=$(sudo docker logs --since 10m $c 2>&1 </dev/null | grep -ciE "traceback|error"); echo "$c error lines: $n"; done
sudo docker exec argus-v18-agent test -f /run/argus-secrets/jwt_ed25519_key </dev/null && echo "mount is a file"
sudo docker exec argus-v18-agent python -c "from argus.infrastructure.wiring import Settings, ed25519_signing_key as k; print('EdDSA on' if k(Settings().secret('jwt_ed25519_key')) else 'EdDSA OFF')" </dev/null
sudo docker exec argus-v18-agent python -c "from argus.capabilities.catalog import build_catalog; print('H5 read registered' if any(s.name == 'analysis.anomaly_summary' for s in build_catalog()) else 'H5 MISSING')" </dev/null
echo "/me without a token: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/api/v1/me </dev/null) (401)"
sudo docker exec argus-v18-agent argus db check </dev/null | grep -E "FAIL|checks passed"
sudo docker exec argus-v18-agent argus audit verify </dev/null | tail -1
OWNER=$(sudo stat -c %u:%g /opt/argus-v18/secrets/postgres/owner_password)
sudo docker run --rm --network argus-v18-core --user "$OWNER" --read-only --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 64 --memory 128m --mount "type=bind,source=/opt/argus-v18/secrets/postgres/owner_password,target=/run/argus-secrets/db_password,readonly" \
  -e ARGUS_DB_BACKEND=postgres -e ARGUS_PG_USER=argus_owner argus-v18-agent:1 python -m argus db prune-sessions </dev/null
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E "^(commit|ref)=|LAB BASELINE"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: three running restarts=0; error lines 0 (a startup line naming a missing optional file is not an error);
#   mount is a file; EdDSA on; H5 read registered; 401; checks passed; the audit chain verified; the dry run lists the
#   sessions it would remove (dry_run true, nothing deleted); ref=afb72e8, LAB BASELINE OK; NO INTERFERENCE.

# --- D.6 [LAPTOP · browser] log in on the UI again: a new EdDSA token; the buttons are a deeper blue ----------------------

# --- D.7 [VM vm-166 · bash] after, then [LAPTOP · PowerShell] release -----------------------------------------------------
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
python brain/tools/brain.py --as conantkd release
# Expected: NO INTERFERENCE; "Lease released on vm-095 and vm-166."
# >>> Paste everything into output.bash and tell the agent "output.bash updated". <<<
