#!/usr/bin/env bash
# The deployment half of the standing write-gate test (T-0031, phase 8, ARCHITECTURE §22.2 and §13.3).
#   on vm-095 (the agent host):  sudo bash /opt/argus-v18/app/ops/write-gate-check.sh
#   on vm-166 (a Host T):        sudo bash /opt/argus-v18/app/ops/write-gate-check.sh --host-only
# Read-only. While no (capability, target) pair is released it checks that nothing on this host can write:
#   - no container named like an action gateway exists (§2 would place it on each Host T);
#   - in each Argus service, the loaded policy's write gate holds exactly the pairs of
#     deploy/action_gateway/first-lab-release.candidate.json (none when that file is absent), the catalogue has no
#     write capability beyond the released ones, and the action gateway's name resolves only when a pair is released
#     (argus/infrastructure/gate_report.py from this checkout, fed to the container's python on stdin with the
#     release file's JSON in ARGUS_RELEASE_JSON, so it checks what the running image loaded even if the image
#     predates it); a gate entry that was not reviewed stops the check; --host-only skips this: a Host T runs no
#     Argus service;
#   - no argus-v18 container mounts an action credential or carries an ARGUS_ACTION* variable, and no file under the
#     deploy home's secrets/ is named like one (names are printed, never values).
# Phase 20 (X-5): once a pair is released the expected state is no longer "nothing", it is exactly the reviewed parts:
#   - on the action host (--host-only, vm-166): only argus-v18-action-proxy and argus-v18-action-gateway, their mounts,
#     their ARGUS_ACTION_ROLE, and the gateway's token at secrets/action/action_token;
#   - on vm-095: no action container; argus-v18-worker may carry ARGUS_ACTION_PATH, ARGUS_ACTION_GATEWAY_URL,
#     ARGUS_ACTION_TOKEN_FILE and ARGUS_ACTION_DAILY_HOST_CAP, and its token is secrets/agent/action_token.
#   Anything else still stops the check. With no released pair everything must be absent, as before.
# Last line: WRITE GATE CLOSED: <what was checked>   or   WRITE GATE AS RELEASED: <n> reviewed pair(s); ...
#            or   WRITE GATE STOP: <reasons>
set -uo pipefail
DOCKER=${ARGUS_DOCKER:-docker}
HOME_DIR=${ARGUS_DEPLOY_HOME:-/opt/argus-v18}
SERVICES=${ARGUS_WRITE_GATE_SERVICES:-"argus-v18-agent argus-v18-worker argus-v18-scheduler"}
HOST_ONLY=0
[ "${1:-}" = "--host-only" ] && SERVICES="" && HOST_ONLY=1
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPORT="$ROOT_DIR/argus/infrastructure/gate_report.py"
RELEASE_FILE=${ARGUS_RELEASE_FILE:-"$ROOT_DIR/deploy/action_gateway/first-lab-release.candidate.json"}
RELEASE_JSON=""; RELEASED=0
if [ -f "$RELEASE_FILE" ]; then
  RELEASE_JSON=$(cat "$RELEASE_FILE")
  RELEASED=$(grep -c '"capability"' "$RELEASE_FILE")
fi
ACTION_CONTAINERS=""; ACTION_FILES=""; WORKER_ENV=""
if [ "$RELEASED" -gt 0 ] && [ "$HOST_ONLY" = 1 ]; then
  ACTION_CONTAINERS="argus-v18-action-proxy argus-v18-action-gateway"
  ACTION_FILES="secrets/action secrets/action/action_token"
elif [ "$RELEASED" -gt 0 ]; then
  ACTION_FILES="secrets/agent/action_token"
  WORKER_ENV="ARGUS_ACTION_PATH ARGUS_ACTION_GATEWAY_URL ARGUS_ACTION_TOKEN_FILE ARGUS_ACTION_DAILY_HOST_CAP"
fi
listed() { case " $2 " in *" $1 "*) return 0 ;; esac; return 1; }     # is word $1 in the list $2
env_ok() {                                                             # may container $1 carry variable $2
  if listed "$1" "$ACTION_CONTAINERS"; then [ "$2" = ARGUS_ACTION_ROLE ]; return; fi
  [ "$1" = argus-v18-worker ] && listed "$2" "$WORKER_ENV"
}
problems=()

containers=$("$DOCKER" ps -a --format '{{.Names}}') \
  || problems+=("docker ps failed: containers not checked")    # never CLOSED on what was not looked at
action=""
for n in $(echo "$containers" | grep -iE 'action'); do listed "$n" "$ACTION_CONTAINERS" || action="$action $n"; done
[ -z "$action" ] || problems+=("action container present: ${action# }")

for c in $SERVICES; do
  line=$("$DOCKER" exec -i ${RELEASE_JSON:+-e "ARGUS_RELEASE_JSON=$RELEASE_JSON"} "$c" python - <"$REPORT" 2>/dev/null | tail -1)
  case "$line" in
    gate_open=*) echo "$c: $line"
                 [[ "$line" == "gate_open=$RELEASED "* && "$line" == *" released_ok=1" ]] \
                   || problems+=("$c: ${line%% policy=*} ${line##* }") ;;
    *) problems+=("$c: no report (container missing or the check failed)") ;;
  esac
done

for c in $(echo "$containers" | grep '^argus-v18-'); do
  if ! listed "$c" "$ACTION_CONTAINERS"; then                    # a released gateway's own mounts are expected
    "$DOCKER" inspect -f '{{range .Mounts}}{{.Source}} {{.Destination}}{{"\n"}}{{end}}' "$c" 2>/dev/null \
      | grep -qi 'action' && problems+=("$c: action mount")
  fi
  names=""
  for v in $("$DOCKER" inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" 2>/dev/null \
             | cut -d= -f1 | grep -E '^ARGUS_ACTION'); do
    env_ok "$c" "$v" || names="$names $v"
  done
  [ -z "$names" ] || problems+=("$c: action environment ${names# }")
done

on_disk=""
for f in $(cd "$HOME_DIR" 2>/dev/null && find secrets -iname '*action*' 2>/dev/null); do
  listed "$f" "$ACTION_FILES" || on_disk="$on_disk $f"
done
[ -z "$on_disk" ] || problems+=("action credential on disk: ${on_disk# }")

if [ ${#problems[@]} -eq 0 ]; then
  checked=${SERVICES:+$(echo $SERVICES | tr ' ' ',') read-only}
  if [ "$RELEASED" -gt 0 ]; then
    echo "WRITE GATE AS RELEASED: $RELEASED reviewed pair(s); ${checked:-host-only}; only the reviewed gateway, its token and the worker's settings"
  else
    echo "WRITE GATE CLOSED: ${checked:-host-only (no Argus service here)}; no action gateway, mount or credential"
  fi
  exit 0
fi
printf '  %s\n' "${problems[@]}"
echo "WRITE GATE STOP: ${#problems[@]} problem(s) listed above"
exit 1
