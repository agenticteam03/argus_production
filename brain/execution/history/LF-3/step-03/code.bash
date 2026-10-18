# (archived) LF-3 step 03, run 2026-10-18 by conantkd's agent over ssh; leases vm-095 + vm-166, session ceeb8c3e6e42.
# Ran: L.0-L.3 and L.6 as written; L.4-L.5 by the developer (browser, hidden prompt); L.7 in the browser; L.8 with two
#   runs of `ops/e2e/run.py SC-02` by the developer (password prompt); L.C executed as written below, with the three
#   image removals added at the developer's request. L.2 deployed 7e6e33c (the head of PR #156) BEFORE its merge, by decision
#   of conantkd: the compose line for ARGUS_TRACING_ENDPOINT is only in that PR. After the merge, the next deploy of
#   main replaces it. See evidence.md and ACR-0016.
# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
# LF-3 step 03 — connect the worker to Langfuse Cloud (EU), ACR-0016                                  [~20 min]
# Runs BEFORE the merge of PR #156 (decision of conantkd): L.2 deploys its approved tip 7e6e33c, which already contains
#   main (merged in) and adds the one compose line. After the merge, the next deploy of main replaces it.
# What changes: vm-095 only. Main's code (compose line for ARGUS_TRACING_ENDPOINT), two worker-only key files, four
#   hosts.env lines, the worker and agent recreated. No Langfuse container, no port, no migration. vm-166: no change.
# Leases: vm-095 + vm-166 (the agent changes). MUTATES vm-095.
# Before L.4: the Langfuse Cloud project (cloud.langfuse.com, region EU, Hobby plan) with its API keys, made by you.
# ROLLBACK (any point): restore /opt/argus-v18/hosts.env.before-lf3cloud, delete the two key files, recreate the
#   worker and agent (L.R). Nothing in Argus's database or audit depends on Langfuse.
# =====================================================================================

# --- L.0 [LAPTOP · PowerShell] both leases, then each VM's session marker -------------------------------------------
python brain/tools/brain.py start --task LF-3 --vm both
#   then, with the session id it prints:
#   [VM vm-095 · bash] and [VM vm-166 · bash]  echo 'holder=conantkd session=<id>' | sudo tee /opt/argus-v18/SESSION >/dev/null

# --- L.1 [VM vm-095 · bash] state probe (read-only) ------------------------------------------------------------------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E '^argus-(v18|lab)-' | sort
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
free -m | awk 'NR==2{print "mem available="$7" MiB"}'; df -h / | awk 'NR==2{print "disk free="$4}'
# Expected: LAB BASELINE OK; the argus-v18-langfuse-* containers stopped or absent (none running); NO INTERFERENCE.
#   If any langfuse container is running: STOP and paste it.

# --- L.2 [VM vm-095 · bash] main + worker/agent, tracing still OFF (MUTATES) -----------------------------------------
ME=conantkd; BR=7e6e33c   # PR #156 tip (main + the ACR-0016 compose line), deployed before its merge
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/db-migrate.sh </dev/null | grep -E "applied|REFUSED|schema:"
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
sudo bash /opt/argus-v18/app/ops/write-gate-check.sh </dev/null | tail -1
cd ~
sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: SESSION OK; NO INTERFERENCE; BACKUP OK; DEPLOY OK: <main commit>; nothing applied; health 200;
#   WRITE GATE CLOSED; LAB BASELINE OK; NO INTERFERENCE.

# --- L.3 [VM vm-095 · bash] Cloud reachable from the worker (read-only) ----------------------------------------------
sudo docker exec argus-v18-worker python -c "import urllib.request as u; print('cloud health', u.urlopen('https://cloud.langfuse.com/api/public/health', timeout=10).status)" </dev/null
# Expected: cloud health 200. Anything else: STOP (egress blocked).

# --- L.4 [BROWSER] the Cloud project -----------------------------------------------------------------------------------
#   https://cloud.langfuse.com (region EU) -> organization "argus" on the Hobby plan -> project "argus-v18"
#   -> Settings -> API keys -> Create: keep the window open for L.5 (the secret key is shown once).
#   Invite the second named user (Hobby allows 2). Note the project id from the URL (/project/<id>): not a secret.

# --- L.5 [VM vm-095 · bash, YOUR terminal: the keys are typed, never pasted into chat or files] (MUTATES) -------------
A=/opt/argus-v18/secrets/agent
read -rsp "Langfuse public key: " PK; echo; read -rsp "Langfuse secret key: " SK; echo
# (vm-095's `install` is uutils: it refuses a numeric owner; umask 377 = born 0400)
printf '%s' "$PK" | sudo sh -c "umask 377; cat > $A/langfuse_public_key"
printf '%s' "$SK" | sudo sh -c "umask 377; cat > $A/langfuse_secret_key"
sudo chown 10010:10010 $A/langfuse_public_key $A/langfuse_secret_key
unset PK SK
sudo stat -c '%a %u %s bytes %n' $A/langfuse_public_key $A/langfuse_secret_key
# Expected: 400 10010, two files of a few dozen bytes (pk-lf-... and sk-lf-...). Never cat them.

# --- L.6 [VM vm-095 · bash] tracing ON for the worker, pointed at Cloud; the trace link for the agent (MUTATES) -------
ME=conantkd
read -rp "Langfuse Cloud project id (from the URL): " PROJECT_ID
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
H=/opt/argus-v18/hosts.env; sudo cp -p $H $H.before-lf3cloud
sudo sed -i '/^ARGUS_TRACING_ENABLED=/d;/^ARGUS_TRACING_ENDPOINT=/d;/^ARGUS_LANGFUSE_UI_URL=/d;/^ARGUS_LANGFUSE_PROJECT_ID=/d' $H
printf 'ARGUS_TRACING_ENABLED=1\nARGUS_TRACING_ENDPOINT=https://cloud.langfuse.com/api/public/otel/v1/traces\nARGUS_LANGFUSE_UI_URL=https://cloud.langfuse.com\nARGUS_LANGFUSE_PROJECT_ID=%s\n' "$PROJECT_ID" | sudo tee -a $H >/dev/null
sudo cut -d= -f1 $H | tr '\n' ' '; echo
cd /opt/argus-v18/app/deploy/vm-095
sudo docker compose --env-file $H -f compose.core.yml up -d --no-deps argus-v18-worker argus-v18-agent </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done; echo "health $c"
sudo docker exec argus-v18-worker sh -c 'echo tracing=$ARGUS_TRACING_ENABLED; echo endpoint=${ARGUS_TRACING_ENDPOINT%%/api*}; ls /run/argus-secrets | grep -c langfuse_' </dev/null
sudo docker logs --tail 20 argus-v18-worker 2>&1 </dev/null | grep -i -E "trac|otlp|langfuse|error" || echo "worker: nothing about tracing yet"
cd ~
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: the four keys in hosts.env; health 200; tracing=1, endpoint=https://cloud.langfuse.com, 2 key files;
#   NO INTERFERENCE. ROLLBACK: L.R.

# --- L.7 [BROWSER] acceptance (ACR-0016 section 6) ------------------------------------------------------------------
#   Argus UI: start a "check" of vm-095/container:argus-lab-api; open the incident -> "Open in Langfuse".
#   Langfuse Cloud: the trace with that incident id: a root agent observation and node spans (a model generation
#   only if the model was called). It may show ONLY: incident id and attempt, class, strategy, outcome, node,
#   capability, status, error category, step, decided_by, evidence id, host inventory name (vm-095/vm-166), target
#   kind, model id, finish reason, token counts, durations. NOT prompts, replies, tool arguments or results, evidence
#   bodies, container or target names, addresses, ports, credentials. Anything else: run L.R and report.

# --- L.8 [VM vm-095 · bash] Cloud unreachable must not change Argus (ACR-0016 section 6) (MUTATES, reversible) --------
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
H=/opt/argus-v18/hosts.env; cd /opt/argus-v18/app/deploy/vm-095
sudo sed -i 's#^ARGUS_TRACING_ENDPOINT=.*#ARGUS_TRACING_ENDPOINT=https://127.0.0.1:9/api/public/otel/v1/traces#' $H   # a closed local port
sudo docker compose --env-file $H -f compose.core.yml up -d --no-deps argus-v18-worker </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
#   (now start one more "check" from the UI and wait for its outcome; its incident, records and audit must be complete)
sudo docker logs --since 5m argus-v18-worker 2>&1 </dev/null | grep -i -E "trac|otlp|drop" | tail -3
sudo sed -i 's#^ARGUS_TRACING_ENDPOINT=.*#ARGUS_TRACING_ENDPOINT=https://cloud.langfuse.com/api/public/otel/v1/traces#' $H
sudo docker compose --env-file $H -f compose.core.yml up -d --no-deps argus-v18-worker </dev/null 2>&1 | grep -E "Recreated|Started" | tr '\n' ' '; echo
cd ~
free -m | awk 'NR==2{print "mem available="$7" MiB"}'; cat /proc/pressure/io | head -1
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
# Expected: the check ended normally; the worker logged the dropped telemetry once; the endpoint is back to Cloud;
#   io pressure low; NO INTERFERENCE.

# --- L.9 [LAPTOP · PowerShell] release --------------------------------------------------------------------------------
python brain/tools/brain.py release

# --- L.R [VM vm-095 · bash] ROLLBACK ----------------------------------------------------------------------------------
# ME=conantkd; H=/opt/argus-v18/hosts.env
# sudo test -f $H.before-lf3cloud && sudo cp -p $H.before-lf3cloud $H && echo "hosts.env restored"
# sudo rm -f /opt/argus-v18/secrets/agent/langfuse_public_key /opt/argus-v18/secrets/agent/langfuse_secret_key
# cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file $H -f compose.core.yml up -d --no-deps argus-v18-worker argus-v18-agent </dev/null 2>&1 | grep -E "Recreated|Started"
# Expected: health 200; tracing=0 in the worker; NO INTERFERENCE. Then revoke the key pair in Langfuse Cloud.

# --- L.C [VM vm-095 · bash] the stopped self-hosted stack, its volumes, images and secrets removed (EXECUTED 2026-10-18) --
# DESTRUCTIVE (only the failed LF-3 trial: no trace was ever ingested). Run on conantkd's explicit request.
ME=conantkd
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
L=/opt/argus-v18/app/deploy/langfuse/compose.yml
sudo docker compose --env-file /opt/argus-v18/secrets/langfuse/runtime.env -f $L down -v --remove-orphans </dev/null 2>&1 | grep -E "Removed|rror"
sudo docker images --format "{{.ID}} {{.Repository}}" | grep -E "docker.langfuse.com/langfuse|clickhouse/clickhouse-server|chainguard/minio" | awk '{print $1}' | sort -u | xargs -r sudo docker image rm -f
sudo rm -rf /opt/argus-v18/secrets/langfuse
# Expected: six containers, five volumes and the network removed; the Langfuse, ClickHouse and MinIO images removed
#   (postgres and redis images are kept: Argus may share them); disk free grows; health 200; NO INTERFERENCE.
