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
# Last line: WRITE GATE CLOSED: <what was checked>   or   WRITE GATE STOP: <reasons>
set -uo pipefail
DOCKER=${ARGUS_DOCKER:-docker}
HOME_DIR=${ARGUS_DEPLOY_HOME:-/opt/argus-v18}
SERVICES=${ARGUS_WRITE_GATE_SERVICES:-"argus-v18-agent argus-v18-worker argus-v18-scheduler"}
[ "${1:-}" = "--host-only" ] && SERVICES=""
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPORT="$ROOT_DIR/argus/infrastructure/gate_report.py"
RELEASE_FILE=${ARGUS_RELEASE_FILE:-"$ROOT_DIR/deploy/action_gateway/first-lab-release.candidate.json"}
RELEASE_JSON=""; RELEASED=0
if [ -f "$RELEASE_FILE" ]; then
  RELEASE_JSON=$(cat "$RELEASE_FILE")
  RELEASED=$(grep -c '"capability"' "$RELEASE_FILE")
fi
problems=()

containers=$("$DOCKER" ps -a --format '{{.Names}}') \
  || problems+=("docker ps failed: containers not checked")    # never CLOSED on what was not looked at
action=$(echo "$containers" | grep -iE 'action' | tr '\n' ' ' | sed 's/ $//')
[ -z "$action" ] || problems+=("action container present: $action")

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
  "$DOCKER" inspect -f '{{range .Mounts}}{{.Source}} {{.Destination}}{{"\n"}}{{end}}' "$c" 2>/dev/null \
    | grep -qi 'action' && problems+=("$c: action mount")
  names=$("$DOCKER" inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" 2>/dev/null \
    | cut -d= -f1 | grep -E '^ARGUS_ACTION' | tr '\n' ' ' | sed 's/ $//')
  [ -z "$names" ] || problems+=("$c: action environment $names")
done

on_disk=$(cd "$HOME_DIR" 2>/dev/null && find secrets -iname '*action*' 2>/dev/null | tr '\n' ' ' | sed 's/ $//')
[ -z "$on_disk" ] || problems+=("action credential on disk: $on_disk")

if [ ${#problems[@]} -eq 0 ]; then
  checked=${SERVICES:+$(echo $SERVICES | tr ' ' ',') read-only}
  echo "WRITE GATE CLOSED: ${checked:-host-only (no Argus service here)}; no action gateway, mount or credential"
  exit 0
fi
printf '  %s\n' "${problems[@]}"
echo "WRITE GATE STOP: ${#problems[@]} problem(s) listed above"
exit 1
