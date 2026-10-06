#!/usr/bin/env bash
# Postgres backup that is proved restorable (T-0017, phase 5 "backup/restore drill"). Run on vm-095:
#   sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as <github-handle>
#       pg_dump of argus-v18-postgres (read-only toward it) into /opt/argus-v18/backups/argus-<UTC>.dump (+ .sha256,
#       + .fingerprint: rows and a content hash per table, taken before and after the dump; they must be equal).
#   sudo bash /opt/argus-v18/app/ops/db-backup.sh verify <dump> --as <github-handle>
#       restores the dump into a throwaway argus-lab-pgrestore (no network, no port, data in tmpfs), compares its
#       fingerprint with the stored one and always removes the container. Never touches the live database.
# A dump holds password hashes (table principal): the folder is 700 and each file 600; a dump never leaves the VM.
# It refuses if /opt/argus-v18/SESSION is not yours. Last line: BACKUP OK / BACKUP STOP / VERIFY OK / VERIFY MISMATCH /
# VERIFY STOP.
set -euo pipefail
HOME_DIR=${ARGUS_DEPLOY_HOME:-/opt/argus-v18}
DOCKER=${ARGUS_DOCKER:-docker}
LIVE=${ARGUS_PG_CONTAINER:-argus-v18-postgres}
RESTORE=${ARGUS_RESTORE_CONTAINER:-argus-lab-pgrestore}
IMAGE=${ARGUS_PG_IMAGE:-postgres:16-alpine}
DIR="$HOME_DIR/backups"

CMD=""; DUMP=""; WHO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --as) shift; WHO="${1:-}" ;;
    backup|verify) CMD=$1 ;;
    *) DUMP=$1 ;;
  esac
  shift
done
STEP=$(echo "${CMD:-BACKUP}" | tr '[:lower:]' '[:upper:]')
stop() { echo "$STEP STOP: $*"; exit 1; }
[ -n "$CMD" ] || stop "usage: db-backup.sh backup --as <handle> | db-backup.sh verify <dump> --as <handle>"
[ -n "$WHO" ] || stop "who are you? add --as <github-handle>"
grep -q "^holder=$WHO " "$HOME_DIR/SESSION" 2>/dev/null \
  || stop "NOT YOUR SESSION: $HOME_DIR/SESSION says '$(head -c 80 "$HOME_DIR/SESSION" 2>/dev/null)' (claim it with brain.py start)"

psql_in() { local c=$1; shift; $DOCKER exec -i -e PGTZ=UTC "$c" psql -X -q -At -v ON_ERROR_STOP=1 -U argus_owner -d argus "$@"; }

# "<table> <rows> <md5 of every row as text, sorted>" for every table in schema public, in name order.
fingerprint() {
  local c=$1 tables
  tables=$(psql_in "$c" -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1" </dev/null)
  [ -n "$tables" ] || return 0
  for t in $tables; do
    echo "SELECT '$t ' || count(*) || ' ' || coalesce(md5(string_agg(x::text, E'\n' ORDER BY x::text)), '-') FROM public.\"$t\" x;"
  done | psql_in "$c"
}

if [ "$CMD" = backup ]; then
  umask 077
  mkdir -p "$DIR"; chmod 700 "$DIR"
  base="$DIR/argus-$(date -u +%Y%m%dT%H%M%SZ)"
  before=$(fingerprint "$LIVE")
  [ -n "$before" ] || stop "no tables found in $LIVE (is it running?)"
  $DOCKER exec "$LIVE" pg_dump -U argus_owner -d argus -Fc > "$base.dump.part" || { rm -f "$base.dump.part"; stop "pg_dump failed"; }
  after=$(fingerprint "$LIVE")
  if [ "$before" != "$after" ]; then
    rm -f "$base.dump.part"
    stop "the database changed during the dump (an investigation was running?); run it again"
  fi
  mv "$base.dump.part" "$base.dump"
  printf '%s\n' "$before" > "$base.fingerprint"
  (cd "$DIR" && sha256sum "$(basename "$base.dump")" > "$(basename "$base.dump").sha256")
  chmod 600 "$base.dump" "$base.fingerprint" "$base.dump.sha256"
  echo "$before" | awk '{t++; r+=$2} END {print "  " t " tables, " r " rows"}'
  echo "BACKUP OK: $base.dump ($(wc -c < "$base.dump") bytes)"
  exit 0
fi

# --- verify ------------------------------------------------------------------------------------------------------
[ -f "$DUMP" ] || stop "no such dump: $DUMP"
[ -f "$DUMP.sha256" ] && [ -f "${DUMP%.dump}.fingerprint" ] || stop "missing $DUMP.sha256 or its .fingerprint"
(cd "$(dirname "$DUMP")" && sha256sum -c --status "$(basename "$DUMP").sha256") || stop "checksum mismatch: $DUMP"
expected=$(cat "${DUMP%.dump}.fingerprint")

cleanup() { $DOCKER rm -f "$RESTORE" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup                                                       # a leftover from an interrupted drill (ours by name)
$DOCKER run -d --name "$RESTORE" --network none --tmpfs /var/lib/postgresql/data:rw,size=256m \
  --memory 384m --memory-swap 384m --cpus 0.4 --pids-limit 100 --label argus.purpose=restore-drill \
  -e POSTGRES_USER=argus_owner -e POSTGRES_DB=argus -e POSTGRES_HOST_AUTH_METHOD=trust "$IMAGE" >/dev/null \
  || stop "could not start $RESTORE"
ready=""
for _ in $(seq 1 60); do                    # the image starts a temporary server first: wait for the real one
  if $DOCKER logs "$RESTORE" 2>&1 | grep -q "init process complete" \
     && $DOCKER exec "$RESTORE" pg_isready -U argus_owner -d argus >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[ -n "$ready" ] || stop "$RESTORE did not become ready in 60 s"
psql_in "$RESTORE" -c "CREATE ROLE argus_runtime NOLOGIN" </dev/null >/dev/null     # the dump's GRANTs need it
$DOCKER exec -i "$RESTORE" pg_restore -U argus_owner -d argus --exit-on-error < "$DUMP" || stop "pg_restore failed"
got=$(fingerprint "$RESTORE")
if [ "$got" != "$expected" ]; then
  echo "  expected (backup)            | restored"
  diff <(echo "$expected") <(echo "$got") || true
  echo "VERIFY MISMATCH: the restored database differs from the backup (lines above)"
  exit 1
fi
echo "$got" | awk '{t++; r+=$2} END {print "VERIFY OK: " t " tables, " r " rows match"}'
