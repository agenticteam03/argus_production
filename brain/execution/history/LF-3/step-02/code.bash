# (archived) LF-3 step 02, run 2026-10-14/15 by conantkd's agent over ssh; leases vm-095 + vm-166, session d7bfceb6737f.
# Ran: L.0-L.3 and L.6 as written; L.5 by the developer (first try failed: uutils install refuses a numeric owner;
#   the block below is the corrected one); L.4 in the browser. L.7-L.8 NOT run: ClickHouse was OOM-killed and the
#   disk saturated, so the stack was stopped and tracing rolled back (L.R in evidence.md). See ACR-0016.
# =====================================================================================
# LF-3 step 02 (2026-10-14, conantkd): vm-095 to main 5d4b347 (#152 ACR-0013 code + #154 record), then the private
#   Langfuse v4 stack (deploy/langfuse/README.md) and the worker's tracing switched on.
# What changes: vm-095 only. The agent image (worker tracing code, trace link), the UI image (Agent page), six new
#   argus-v18-langfuse-* containers with their own volumes, two worker-only key files, three hosts.env lines.
#   vm-166: no change (no target-service change since 37822c9); its lease is held because the agent changes.
# Leases: vm-095 + vm-166. MUTATES vm-095.
# ROLLBACK (any point): restore /opt/argus-v18/hosts.env.before-lf3 and recreate the worker and agent;
#   `docker compose -f /opt/argus-v18/app/deploy/langfuse/compose.yml down` (volumes kept);
#   code: deploy.sh 37822c9 --as conantkd, then the L.2 compose commands.
# Order: L.0 laptop -> L.1 both VMs -> L.2 vm-095 -> L.3 vm-095 -> L.4 laptop+browser -> L.5 vm-095 (YOUR terminal)
#   -> L.6 vm-095 -> L.7 UI + Langfuse -> L.8 vm-095 -> L.9 laptop.
# =====================================================================================

# --- L.0 [LAPTOP · PowerShell] both leases, then each VM's session marker -------------------------------------------
python brain/tools/brain.py start --task LF-3 --vm both
#   then, with the session id it prints:
#   [VM vm-095 · bash] and [VM vm-166 · bash]  echo 'holder=conantkd session=<id>' | sudo tee /opt/argus-v18/SESSION >/dev/null

# --- L.1 [VM vm-095 · bash] and [VM vm-166 · bash] state probe (read-only) -------------------------------------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E '^argus-(v18|lab)-' | sort
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
free -m | awk 'NR==2{print "mem total="$2" available="$7" MiB"}'; df -h / | awk 'NR==2{print "disk free="$4}'
# Expected: vm-095 commit=37822c9 ref=main, LAB BASELINE OK, NO INTERFERENCE, available >= 3500 MiB.
#   vm-166 is not changed here; its lab state (argus-lab-cache stopped since 22:07Z) is reported, not repaired.

# --- L.2 [VM vm-095 · bash] main + agent/worker/scheduler + UI, tracing still OFF (MUTATES) ---------------------------
ME=conantkd; BR=main
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "applied|REFUSED|schema:"
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do echo "$c image=$(sudo docker inspect -f '{{.Image}}' $c </dev/null | cut -c8-19) $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c </dev/null)"; done
sudo docker logs --tail 5 argus-v18-worker 2>&1 </dev/null | grep -i -E "startup validation|missing credential|error" || echo "worker: no startup errors"
sudo docker exec argus-v18-agent argus db check </dev/null | tail -1
sudo docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py </dev/null | grep -E "checks passed|FAIL"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
cd /opt/argus-v18/app/deploy/ui
sudo docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml up -d --build </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 30); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-v18-ui </dev/null 2>/dev/null); [ "$s" = healthy ] && break; sleep 3; done
echo "ui: $(sudo docker inspect -f '{{.State.Status}} health={{.State.Health.Status}} restarts={{.RestartCount}}' argus-v18-ui </dev/null)"
for p in /api/v1/me /docs; do echo "GET $p $(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1$p </dev/null)"; done
cd ~
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: SESSION OK; NO INTERFERENCE; BACKUP OK; DEPLOY OK: 5d4b347... (main); schema 001-006, nothing applied;
#   the three on ONE image, restarts=0; health 200; no startup errors; 20/20; 55/55; WRITE GATE CLOSED;
#   ui healthy; /me 401, /docs 404; commit=5d4b347 ref=main; LAB BASELINE OK; NO INTERFERENCE.

# --- L.3 [VM vm-095 · bash] Langfuse secrets (generated here, never printed) and the stack (MUTATES) -----------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
S=/opt/argus-v18/secrets/langfuse; sudo install -d -m 0700 -o root -g root $S
if sudo test -s $S/runtime.env; then echo "runtime.env exists: kept"; else
  sudo sh -c "umask 077; { for v in LF_POSTGRES_PASSWORD LF_CLICKHOUSE_PASSWORD LF_REDIS_PASSWORD LF_MINIO_USER LF_MINIO_PASSWORD LF_SALT LF_NEXTAUTH_SECRET; do echo \"\$v=\$(openssl rand -hex 24)\"; done; echo \"LF_ENCRYPTION_KEY=\$(openssl rand -hex 32)\"; } > $S/runtime.env"
  echo "runtime.env written: $(sudo grep -c '=' $S/runtime.env) values"; fi
sudo stat -c '%a %U %n' $S/runtime.env
L=/opt/argus-v18/app/deploy/langfuse/compose.yml
sudo docker compose --env-file $S/runtime.env -f $L pull -q </dev/null 2>&1 | tail -2
sudo docker compose --env-file $S/runtime.env -f $L up -d </dev/null 2>&1 | grep -E "Started|Running|Healthy|Error" | tr '\n' ' '; echo
for i in $(seq 1 60); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18300/api/public/health </dev/null); [ "$c" = 200 ] && break; sleep 10; done; echo "langfuse health $c after ~$((i*10)) s"
sudo docker ps --format '{{.Names}} {{.Status}}' | grep langfuse | sort
sudo docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' | grep langfuse | sort
free -m | awk 'NR==2{print "mem available="$7" MiB"}'
for i in $(seq 1 6); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "argus health $c"
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: runtime.env 600 root (8 values); six argus-v18-langfuse-* running (healthy where they have a check);
#   langfuse health 200; mem available >= 1000 MiB; argus health 200; nonint: the ONE expected difference is
#   the new listener '> tcp 127.0.0.1:18300' (Langfuse web, an Argus port); anything else: STOP.
#   ClickHouse migrations make the first start slow on 1 vCPU: up to 10 minutes is normal.

# --- L.4 [LAPTOP · PowerShell + browser] the first account and project, through a tunnel -----------------------------
ssh -N -L 18300:127.0.0.1:18300 argus-vm095
#   Browser: http://localhost:18300 -> Sign up (your own account) -> organization "argus" -> project "argus-v18".
#   Project settings -> API keys -> Create: keep the window open for L.5 (the secret key is shown once).
#   Note the project id from the URL (/project/<id>/...): it is not a secret.

# --- L.5 [VM vm-095 · bash, YOUR terminal: the keys are typed, never pasted into chat or files] (MUTATES) -------------
A=/opt/argus-v18/secrets/agent
read -rsp "Langfuse public key: " PK; echo; read -rsp "Langfuse secret key: " SK; echo
# (vm-095's `install` is uutils: it refuses a numeric owner, "invalid user: '10010'"; umask 377 = born 0400)
printf '%s' "$PK" | sudo sh -c "umask 377; cat > $A/langfuse_public_key"
printf '%s' "$SK" | sudo sh -c "umask 377; cat > $A/langfuse_secret_key"
sudo chown 10010:10010 $A/langfuse_public_key $A/langfuse_secret_key
unset PK SK
sudo stat -c '%a %u %s bytes %n' $A/langfuse_public_key $A/langfuse_secret_key
# Expected: 400 10010, two files of a few dozen bytes (pk-lf-... and sk-lf-...). Never cat them.

# --- L.6 [VM vm-095 · bash] tracing ON for the worker; the trace link for the agent (MUTATES) -------------------------
ME=conantkd; PROJECT_ID=REPLACE_WITH_THE_ID_FROM_L4
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
H=/opt/argus-v18/hosts.env; sudo cp -p $H $H.before-lf3
sudo sed -i '/^ARGUS_TRACING_ENABLED=/d;/^ARGUS_LANGFUSE_UI_URL=/d;/^ARGUS_LANGFUSE_PROJECT_ID=/d' $H
printf 'ARGUS_TRACING_ENABLED=1\nARGUS_LANGFUSE_UI_URL=http://localhost:18300\nARGUS_LANGFUSE_PROJECT_ID=%s\n' "$PROJECT_ID" | sudo tee -a $H >/dev/null
sudo cut -d= -f1 $H | tr '\n' ' '; echo
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file $H -f compose.core.yml up -d --no-deps argus-v18-worker argus-v18-agent </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
sudo docker exec argus-v18-worker sh -c 'echo tracing=$ARGUS_TRACING_ENABLED; ls /run/argus-secrets | grep -c langfuse_' </dev/null
sudo docker logs --tail 20 argus-v18-worker 2>&1 </dev/null | grep -i -E "trac|otlp|langfuse|error" || echo "worker: nothing about tracing yet"
cd ~
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: hosts.env keys now include the three; health 200; tracing=1 and 2 key files; NO INTERFERENCE.
#   ROLLBACK: sudo cp -p $H.before-lf3 $H, then the same compose command.

# --- L.7 [BROWSER] acceptance (README steps 3-4) ---------------------------------------------------------------------
#   Argus UI (new login): start a "check" of vm-095/container:argus-lab-api; open the incident -> "Open in Langfuse".
#   Langfuse (tunnel): the trace with that incident id: a root agent observation and node spans (a model generation
#   only if the model was called). It must NOT show prompts, replies, evidence bodies, target or host names, secrets.

# --- L.8 [VM vm-095 · bash] Langfuse away must not change Argus (README step 5), then the measures (MUTATES) ---------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo docker compose --env-file /opt/argus-v18/secrets/langfuse/runtime.env -f /opt/argus-v18/app/deploy/langfuse/compose.yml stop argus-v18-langfuse-web </dev/null 2>&1 | tail -1   # the service name: compose sets no container_name
#   (now start one more "check" from the UI and wait for its outcome; then continue)
sudo docker logs --since 5m argus-v18-worker 2>&1 </dev/null | grep -i -E "trac|otlp|drop" | tail -3
sudo docker compose --env-file /opt/argus-v18/secrets/langfuse/runtime.env -f /opt/argus-v18/app/deploy/langfuse/compose.yml start argus-v18-langfuse-web </dev/null 2>&1 | tail -1
for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18300/api/public/health </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "langfuse health $c"
sudo docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' | grep -E 'argus-v18' | sed 's/argus-v18-langfuse-argus-v18-/lf:/' | sort
free -m | awk 'NR==2{print "mem available="$7" MiB"}'; cat /proc/pressure/memory | head -1; cat /proc/pressure/cpu | head -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: the check during the stop ended normally (its incident and audit complete); the worker logged the
#   dropped telemetry once; langfuse health 200 again; memory available >= 1000 MiB; nonint: only the 18300 line.

# --- L.D [VM vm-095 · bash] diagnosis while L.6 hung (read-only) ----------------------------------------------------
uptime; cat /proc/pressure/cpu | head -1; cat /proc/pressure/memory | head -1; cat /proc/pressure/io | head -1
ps -eo pcpu,rss,comm --sort=-pcpu | head -8
sudo journalctl -k --since "-1h" --no-pager | grep -i -E "oom|killed process|memory cgroup" | tail -8
sudo docker inspect -f "{{.Name}} oom={{.State.OOMKilled}} restarts={{.RestartCount}} exit={{.State.ExitCode}}" $(sudo docker ps -aq --filter name=langfuse)

# --- L.R [VM vm-095 · bash] stop the stack (volumes kept), tracing off, keys removed (MUTATES; README "capacity") ------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo docker compose --env-file /opt/argus-v18/secrets/langfuse/runtime.env -f /opt/argus-v18/app/deploy/langfuse/compose.yml stop </dev/null 2>&1 | tail -7
H=/opt/argus-v18/hosts.env; sudo test -f $H.before-lf3 && sudo cp -p $H.before-lf3 $H && echo "hosts.env restored"
sudo rm -f /opt/argus-v18/secrets/agent/langfuse_public_key /opt/argus-v18/secrets/agent/langfuse_secret_key
cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file $H -f compose.core.yml up -d --no-deps argus-v18-worker argus-v18-agent </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
sudo docker exec argus-v18-worker sh -c 'echo tracing=$ARGUS_TRACING_ENABLED' </dev/null
cd ~; sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1; uptime
# Expected: the six stopped (not removed); hosts.env without the three ACR-0013 lines; no key file; health 200;
#   tracing=0; NO INTERFERENCE; load falling.

# --- L.C [VM vm-095 · bash] egress to Langfuse Cloud from the worker (read-only; for ACR-0016) ----------------------
sudo docker exec argus-v18-worker python -c "
import urllib.request
for u in ('https://cloud.langfuse.com/api/public/health', 'https://us.cloud.langfuse.com/api/public/health'):
    try: r = urllib.request.urlopen(u, timeout=8); print(u, r.status, r.read()[:80])
    except Exception as e: print(u, 'ERR', e)
" </dev/null

# --- L.9 [LAPTOP · PowerShell] release both leases ------------------------------------------------------------------
python brain/tools/brain.py release
