#!/usr/bin/env bash
# OP-004: one-off Argus maintenance command, with only the Postgres owner secret mounted.
# Manual: sudo bash ops/checkpoint-retention.sh --dry-run --as <lease holder>
# Timer:  systemd calls --apply --scheduled after VM verification and approval.
set -euo pipefail

HOME_DIR=${ARGUS_DEPLOY_HOME:-/opt/argus-v18}
DOCKER=${ARGUS_DOCKER:-docker}
IMAGE=${ARGUS_MAINTENANCE_IMAGE:-argus-v18-agent:1}
SECRET="$HOME_DIR/secrets/postgres/owner_password"
DAYS=${ARGUS_CHECKPOINT_RETENTION_DAYS:-30}
MODE=--dry-run
WHO=""
SCHEDULED=false

stop() { echo "CHECKPOINT RETENTION STOP: $*"; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run|--apply) MODE=$1 ;;
    --as) shift; WHO=${1:-} ;;
    --scheduled) SCHEDULED=true ;;
    *) stop "unknown argument $1" ;;
  esac
  shift
done

[[ "$DAYS" =~ ^[1-9][0-9]*$ ]] || stop "ARGUS_CHECKPOINT_RETENTION_DAYS must be positive"
[ -s "$SECRET" ] || stop "owner credential missing"
if [ "$SCHEDULED" = false ]; then
  [ -n "$WHO" ] || stop "manual run needs --as <lease holder>"
  grep -q "^holder=$WHO " "$HOME_DIR/SESSION" 2>/dev/null || stop "NOT YOUR SESSION"
else
  [ -z "$WHO" ] || stop "--scheduled cannot be combined with --as"
fi

ARGS=(db prune-checkpoints --days "$DAYS")
[ "$MODE" = --apply ] && ARGS+=(--apply)
"$DOCKER" run --rm --network argus-v18-core --user 0:0 --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 64 --memory 128m \
  --mount "type=bind,source=$SECRET,target=/run/argus-secrets/db_password,readonly" \
  -e ARGUS_DB_BACKEND=postgres -e ARGUS_PG_USER=argus_owner \
  "$IMAGE" python -m argus "${ARGS[@]}"
