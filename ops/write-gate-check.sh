#!/usr/bin/env bash
# The deployment half of the standing write-gate test (T-0031, phase 8, ARCHITECTURE §22.2 and §13.3). Run on vm-095:
#   sudo bash /opt/argus-v18/app/ops/write-gate-check.sh
# Read-only. While no (capability, target) pair is released it checks that nothing on this host can write:
#   - no container named like an action gateway exists;
#   - in each Argus service, the loaded policy has an empty write gate, the catalogue has no write capability and
#     the action gateway's name does not resolve (argus/policy/gate_report.py from this checkout, fed to the
#     container's python on stdin, so it checks what the running image loaded even if the image predates it);
#   - no service mounts an action credential or carries an ARGUS_ACTION* variable (names are printed, never values).
# Last line: WRITE GATE CLOSED: <services checked>   or   WRITE GATE STOP: <reasons>
set -uo pipefail
DOCKER=${ARGUS_DOCKER:-docker}
SERVICES=${ARGUS_WRITE_GATE_SERVICES:-"argus-v18-agent argus-v18-worker argus-v18-scheduler"}
REPORT="$(cd "$(dirname "$0")/.." && pwd)/argus/policy/gate_report.py"
problems=()

action=$("$DOCKER" ps -a --format '{{.Names}}' | grep -iE 'action' | tr '\n' ' ' | sed 's/ $//')
[ -z "$action" ] || problems+=("action container present: $action")

for c in $SERVICES; do
  line=$("$DOCKER" exec -i "$c" python - <"$REPORT" 2>/dev/null | tail -1)
  case "$line" in
    gate_open=*) echo "$c: $line"
                 [[ "$line" == "gate_open=0 write_capabilities=0 action_gateway_resolves=0 "* ]] \
                   || problems+=("$c: ${line% policy=*}") ;;
    *) problems+=("$c: no report (container missing or the check failed)") ;;
  esac
  "$DOCKER" inspect -f '{{range .Mounts}}{{.Source}} {{.Destination}}{{"\n"}}{{end}}' "$c" 2>/dev/null \
    | grep -qi 'action' && problems+=("$c: action mount")
  names=$("$DOCKER" inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" 2>/dev/null \
    | cut -d= -f1 | grep -E '^ARGUS_ACTION' | tr '\n' ' ' | sed 's/ $//')
  [ -z "$names" ] || problems+=("$c: action environment $names")
done

if [ ${#problems[@]} -eq 0 ]; then
  echo "WRITE GATE CLOSED: $(echo $SERVICES | tr ' ' ',') read-only; no action gateway, mount or credential"
  exit 0
fi
printf '  %s\n' "${problems[@]}"
echo "WRITE GATE STOP: ${#problems[@]} problem(s) listed above"
exit 1
