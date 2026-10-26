# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
#   [VM vm-095 · bash]      ssh argus-vm095
#   [VM vm-166 · bash]      ssh argus-vm166
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated".
# =====================================================================================

# =====================================================================================
# STEP DEPLOY-798b69a — phase 16's security alerts to Telegram and the scheduler's egress proxy (#344)   [~35 min]
# Goal / Why: main 798b69a brings #344: the scheduler posts security events to vm-095's Alertmanager, which sends them
#   to the team's Telegram group through argus-v18-egress (tinyproxy: CONNECT :443 to OCI Object Storage and the
#   Telegram API only); the scheduler moves to argus-v18-sched (internal, no route out). No migration (schema 001-016),
#   no UI change. Postgres and the tunnel are recreated to join argus-v18-sched (a short database restart).
# MUTATES: vm-095 (a backup, the checkout to 798b69a, two secret files, the network argus-v18-sched, the egress image
#   and container, postgres/tunnel/agent/worker/scheduler recreated, prometheus/alertmanager recreated, a deploy
#   event, one test security alert). vm-166: the marker and two snapshots only.
# ROLLBACK (vm-095, in this order):
#   sudo bash /opt/argus-v18/app/ops/deploy.sh 6e87828 --as conantkd
#   cd /opt/argus-v18/app/deploy/vm-095 && sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml \
#     up -d --build argus-v18-postgres argus-v18-tunnel argus-v18-agent argus-v18-worker argus-v18-scheduler && cd ~
#   sudo docker rm -f argus-v18-egress
#   cd /opt/argus-v18/app/deploy/monitoring && sudo docker compose --env-file vm-095.env -f compose.monitoring.yml \
#     -f compose.core-join.yml up -d && cd ~
#   sudo docker network rm argus-v18-sched
#   (the secret files may stay: nothing reads them at 6e87828). The backup of D.2 is the last resort.
# =====================================================================================

# --- D.1 [VM vm-166 · bash] (ssh argus-vm166) marker and "before" (MUTATES: the marker and a snapshot) ----------------
echo 'holder=conantkd session=3d07ee84ec5e' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  echo "VERDICT: D.1 PASS"
else
  echo "VERDICT: D.1 STOP: NOT YOUR SESSION"
fi
# Expected: a "before" snapshot line; VERDICT: D.1 PASS.

# --- D.2 [VM vm-095 · bash] (ssh argus-vm095) marker, no running evaluation, backup, checkout 798b69a (MUTATES) --------
echo 'holder=conantkd session=3d07ee84ec5e' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  RUNNING=$(pgrep -af 'argus.evaluation|argus evaluate' | grep -v pgrep | wc -l)
  echo "evaluations running: $RUNNING"
  if [ "$RUNNING" -ne 0 ]; then
    echo "VERDICT: D.2 STOP: an evaluation is still running (nothing changed)"
  else
    sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as conantkd </dev/null | tail -1
    sudo bash /opt/argus-v18/app/ops/db-backup.sh verify latest --as conantkd </dev/null | tail -1
    OUT=$(sudo bash /opt/argus-v18/app/ops/deploy.sh 798b69a --as conantkd </dev/null 2>&1)
    echo "$OUT" | tail -4
    case "$OUT" in
      *"DEPLOY OK"*) echo "VERDICT: D.2 PASS" ;;
      *) echo "VERDICT: D.2 STOP: deploy.sh did not say DEPLOY OK" ;;
    esac
  fi
else
  echo "VERDICT: D.2 STOP: NOT YOUR SESSION"
fi
# Expected: ref=6e87828, LAB BASELINE OK; a "before" line; evaluations running: 0; BACKUP OK; VERIFY OK;
#   DEPLOY OK: 798b69a...; VERDICT: D.2 PASS.

# --- D.3 [VM vm-095 · bash] the Telegram bot token and chat id (MUTATES: two secret files; YOU type the token) ---------
# Before: the bot is in the team's group and someone wrote a message in the group after adding it (getUpdates only
# lists chats with a recent update). The token is typed at a hidden prompt, never echoed, never in a command line
# (curl reads its URL from stdin). Safe to re-run: an existing token file is reused, the prompt is skipped.
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  D=/opt/argus-v18/secrets/alertmanager
  sudo install -d -o 65534 -g 65534 -m 0500 "$D"
  if sudo test -s "$D/telegram_bot_token"; then
    T=$(sudo cat "$D/telegram_bot_token"); echo "token file: present (reused)"
  else
    read -rsp "Telegram bot token (hidden): " T; echo
    printf '%s' "$T" | sudo tee "$D/telegram_bot_token" >/dev/null
    echo "token file: written"
  fi
  CHATS=$(printf 'url = "https://api.telegram.org/bot%s/getUpdates"\n' "$T" | curl -s --max-time 15 -K - \
    | python3 -c 'import json,sys
d=json.load(sys.stdin); ok=d.get("ok")
seen={}
for u in d.get("result", []):
    for k in ("message","my_chat_member","channel_post"):
        c=(u.get(k) or {}).get("chat") or {}
        if c.get("type") in ("group","supergroup"): seen[c["id"]]=c.get("title","")
print("ok" if ok else "notok"); [print(i, t, sep="\t") for i, t in seen.items()]')
  unset T
  echo "Telegram API: $(echo "$CHATS" | head -1)"
  N=$(echo "$CHATS" | tail -n +2 | grep -c .)
  echo "groups seen: $N  ($(echo "$CHATS" | tail -n +2 | cut -f2 | paste -sd ','))"
  if [ "$N" -eq 1 ]; then
    echo "$CHATS" | tail -n +2 | cut -f1 | tr -d '\n' | sudo tee "$D/telegram_chat_id" >/dev/null
    sudo chown 65534:65534 "$D/telegram_bot_token" "$D/telegram_chat_id"
    sudo chmod 0400 "$D/telegram_bot_token" "$D/telegram_chat_id"
    sudo ls -l "$D" | awk 'NR>1 {print $1, $3, $NF}'
    echo "VERDICT: D.3 PASS"
  else
    echo "VERDICT: D.3 STOP: need exactly one group (write a message in the group, wait a minute, re-run D.3)"
  fi
else
  echo "VERDICT: D.3 STOP: NOT YOUR SESSION"
fi
# Expected: token file written (or reused); Telegram API: ok; groups seen: 1 (the group's name); two files
#   -r-------- 65534 (or nobody); VERDICT: D.3 PASS. Do NOT go on to D.5 without D.3 PASS: the Alertmanager would
#   not start without the files.

# --- D.4 [VM vm-095 · bash] the core: network, egress, postgres, tunnel, agent, worker, scheduler (MUTATES) ------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  cd /opt/argus-v18/app/deploy/vm-095
  sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --build \
    argus-v18-postgres argus-v18-tunnel argus-v18-egress argus-v18-agent argus-v18-worker argus-v18-scheduler \
    </dev/null 2>&1 | grep -E "Network|Recreated|Created|Started|rror"
  cd ~
  for i in $(seq 1 30); do c=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:18000/healthz </dev/null); [ "$c" = 200 ] && break; sleep 5; done
  echo "health $c"
  echo "sched internal: $(sudo docker network inspect -f '{{.Internal}}' argus-v18-sched </dev/null)"
  echo "scheduler networks: $(sudo docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' argus-v18-scheduler </dev/null)"
  sudo docker exec argus-v18-agent argus deploy record --commit 798b69a --ref main --as conantkd </dev/null | tail -1
  [ "$c" = 200 ] && echo "VERDICT: D.4 PASS" || echo "VERDICT: D.4 STOP: health $c"
else
  echo "VERDICT: D.4 STOP: NOT YOUR SESSION"
fi
# Expected: Network argus-v18-sched Created; egress built and Started; the others Recreated/Started; no "rror";
#   health 200; sched internal: true; scheduler networks: argus-v18-sched (only); deploy recorded; VERDICT: D.4 PASS.

# --- D.5 [VM vm-095 · bash] monitoring: Prometheus and Alertmanager join argus-v18-sched (MUTATES) ---------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  if sudo test -s /opt/argus-v18/secrets/alertmanager/telegram_chat_id; then
    cd /opt/argus-v18/app/deploy/monitoring
    sudo docker compose --env-file vm-095.env -f compose.monitoring.yml -f compose.core-join.yml up -d \
      </dev/null 2>&1 | grep -E "Recreated|Started|rror"
    cd ~
    sleep 15
    for c in argus-v18-prometheus argus-v18-alertmanager; do echo "$c $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c </dev/null)"; done
    n=$(sudo docker logs --since 2m argus-v18-alertmanager 2>&1 </dev/null | grep -ciE "level=(error|warn)|err=")
    echo "alertmanager error/warn lines: $n"
    [ "$n" -eq 0 ] && echo "VERDICT: D.5 PASS" || echo "VERDICT: D.5 STOP: alertmanager logged $n error/warn line(s)"
  else
    echo "VERDICT: D.5 STOP: no chat id file (run D.3 first; nothing changed)"
  fi
else
  echo "VERDICT: D.5 STOP: NOT YOUR SESSION"
fi
# Expected: prometheus and alertmanager Recreated/Started; both running restarts=0; alertmanager error/warn lines: 0;
#   VERDICT: D.5 PASS.

# --- D.6 [VM vm-095 · bash] checks: egress, a test alert to Telegram, logs, database, audit (MUTATES: one test alert) --
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler argus-v18-egress argus-v18-ui; do echo "$c $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' $c </dev/null)"; done
  sudo docker exec argus-v18-scheduler python -c '
import httpx
for host in ("api.telegram.org", "github.com", "api.openai.com"):
    try:
        r = httpx.get(f"https://{host}/", timeout=10)
        print("via proxy", host, "reached", r.status_code)
    except Exception as e:
        print("via proxy", host, "refused", type(e).__name__)
try:
    httpx.get("https://api.telegram.org/", timeout=8, trust_env=False)
    print("direct reached (BAD)")
except Exception as e:
    print("direct refused", type(e).__name__)
' </dev/null
  echo "egress filtered: $(sudo docker logs --since 5m argus-v18-egress 2>&1 </dev/null | grep -ci 'filtered')"
  sudo docker exec argus-v18-scheduler python -c '
import datetime, httpx
now = datetime.datetime.now(datetime.timezone.utc)
a = [{"labels": {"alertname": "ArgusSecurityEvent", "argus_security": "true", "event": "deploy.test",
                 "audit_id": "deploy-798b69a-test"},
      "annotations": {"summary": "DEPLOY-798b69a test: not a real event, ignore"},
      "startsAt": now.isoformat(), "endsAt": (now + datetime.timedelta(minutes=10)).isoformat()}]
print("test alert posted", httpx.post("http://argus-v18-alertmanager:9093/api/v2/alerts", json=a, timeout=10).status_code)
' </dev/null
  sleep 40
  echo "notify failures: $(sudo docker logs --since 2m argus-v18-alertmanager 2>&1 </dev/null | grep -ci 'notify.*fail\|Notify for alerts failed')"
  sleep 30
  for c in argus-v18-agent argus-v18-worker argus-v18-scheduler; do n=$(sudo docker logs --since 10m $c 2>&1 </dev/null | grep -v argus_probe_error | grep -ciE "traceback|error"); echo "$c error lines: $n"; done
  sudo docker logs --since 10m argus-v18-scheduler 2>&1 </dev/null | grep -E "security alert|audit digest|audit chain" | tail -4
  sudo docker exec argus-v18-agent argus db check </dev/null | grep -E "FAIL|checks passed"
  sudo docker exec argus-v18-agent argus audit verify </dev/null | tail -1
  echo "public ops: $(curl -s -o /dev/null -w '%{http_code}' https://$(grep -E '^ARGUS_UI_DOMAIN=' /opt/argus-v18/app/deploy/ui/vm-095.env | cut -d= -f2)/api/v1/ops/ </dev/null)"
  # (corrected after the run: the domain is in deploy/ui/vm-095.env, not hosts.env; the run printed 000, re-read: 404)
  sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
  echo "VERDICT: D.6 DONE (read the lines above; the agent checks them)"
else
  echo "VERDICT: D.6 STOP: NOT YOUR SESSION"
fi
# Expected: all running restarts=0; via proxy api.telegram.org reached <code>; github.com and api.openai.com refused;
#   direct refused; egress filtered >= 2; test alert posted 200; notify failures: 0; THE TEAM'S TELEGRAM GROUP SHOWS
#   "Argus security: DEPLOY-798b69a test: not a real event, ignore"; error lines 0; a "security alert(s)" log line;
#   database "checks passed" (no FAIL); audit verify ok; public ops: 404; ref=798b69a, LAB BASELINE OK;
#   NO INTERFERENCE.

# --- D.7 [VM vm-166 · bash] (ssh argus-vm166) "after" (READ-ONLY) ------------------------------------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
  echo "VERDICT: D.7 PASS"
else
  echo "VERDICT: D.7 STOP: NOT YOUR SESSION"
fi
# Expected: NO INTERFERENCE; VERDICT: D.7 PASS.
# >>> Paste everything into output.bash and tell the agent "output.bash updated". <<<
