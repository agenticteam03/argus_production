#!/usr/bin/env bash
# Postgres backup that is proved restorable (T-0017, phase 5 "backup/restore drill"). Run on vm-095:
#   sudo bash /opt/argus-v18/app/ops/db-backup.sh backup --as <github-handle>
#       pg_dump of argus-v18-postgres (read-only toward it) into /opt/argus-v18/backups/argus-<UTC>.dump (+ .sha256,
#       + .fingerprint: rows and a content hash per table from the same exported snapshot as pg_dump).
#   sudo bash /opt/argus-v18/app/ops/db-backup.sh verify <dump>|latest --as <github-handle>
#       restores the dump into a throwaway argus-lab-pgrestore (no network, no port, data in tmpfs), compares its
#       fingerprint with the stored one and always removes the container. Never touches the live database.
#   sudo bash /opt/argus-v18/app/ops/db-backup.sh prune --as <github-handle> [--apply]
#       previews old backup sets by default; --apply removes them while keeping the newest N and newest verified.
# A dump holds password hashes (table principal): the folder is 700 and each file 600; a dump never leaves the VM.
# It refuses if /opt/argus-v18/SESSION is not yours. Last line reports BACKUP, VERIFY, or PRUNE status.
set -euo pipefail
HOME_DIR=${ARGUS_DEPLOY_HOME:-/opt/argus-v18}
DOCKER=${ARGUS_DOCKER:-docker}
LIVE=${ARGUS_PG_CONTAINER:-argus-v18-postgres}
RESTORE=${ARGUS_RESTORE_CONTAINER:-argus-lab-pgrestore}
IMAGE=${ARGUS_PG_IMAGE:-postgres:16-alpine}
DIR="$HOME_DIR/backups"

CMD=""; DUMP=""; WHO=""; APPLY=false
while [ $# -gt 0 ]; do
  case "$1" in
    --as) shift; WHO="${1:-}" ;;
    --apply) APPLY=true ;;
    backup|verify|prune) CMD=$1 ;;
    *) DUMP=$1 ;;
  esac
  shift
done
STEP=$(echo "${CMD:-BACKUP}" | tr '[:lower:]' '[:upper:]')
stop() { echo "$STEP STOP: $*"; exit 1; }
[ -n "$CMD" ] || stop "usage: db-backup.sh backup | verify <dump> | prune [--apply] --as <handle>"
[ -n "$WHO" ] || stop "who are you? add --as <github-handle>"
grep -q "^holder=$WHO " "$HOME_DIR/SESSION" 2>/dev/null \
  || stop "NOT YOUR SESSION: $HOME_DIR/SESSION says '$(head -c 80 "$HOME_DIR/SESSION" 2>/dev/null)' (claim it with brain.py start)"
[ "$CMD" = prune ] || { [ "$APPLY" = false ] || stop "--apply is only valid with prune"; }

if [ "$CMD" = prune ]; then
  KEEP=${ARGUS_BACKUP_KEEP:-7}
  [[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || stop "ARGUS_BACKUP_KEEP must be a positive integer"
  [ ! -L "$DIR" ] || stop "backups directory must not be a symlink"
  [ -d "$DIR" ] || { echo "PRUNE $([ "$APPLY" = true ] && echo OK || echo 'DRY RUN'): no backups"; exit 0; }
  mapfile -t candidates < <(find "$DIR" -maxdepth 1 -type f -name 'argus-*.dump' -printf '%f\n' | LC_ALL=C sort -r)
  dumps=()
  for name in "${candidates[@]}"; do
    [[ "$name" =~ ^argus-[0-9]{8}T[0-9]{6}Z\.dump$ ]] && dumps+=("$name")
  done
  # A .verified marker protects a set only while its dump still matches the checksum it was verified with.
  newest_verified=""
  for name in "${dumps[@]}"; do
    base="$DIR/${name%.dump}"
    [ -f "$base.verified" ] || continue
    if [ -f "$base.dump.sha256" ] && (cd "$DIR" && sha256sum -c --status "$name.sha256" 2>/dev/null); then
      newest_verified=$name; break
    fi
    echo "  verified but checksum mismatch: $name"
  done
  echo "  newest verified (kept): ${newest_verified:-none}"
  # Leftovers (a killed run's .part, set files whose dump is gone) are listed for a human, never removed here.
  leftovers=0
  while IFS= read -r name; do
    case "$name" in
      *.dump.part) ;;
      *.dump.sha256) [ ! -e "$DIR/${name%.sha256}" ] || continue ;;
      *.fingerprint|*.verified) [ ! -e "$DIR/${name%.*}.dump" ] || continue ;;
      *) continue ;;
    esac
    echo "  leftover (not removed): $name"
    leftovers=$((leftovers + 1))
  done < <(find "$DIR" -maxdepth 1 -type f -name 'argus-*' -printf '%f\n' | LC_ALL=C sort)
  [ "$leftovers" -eq 0 ] || echo "  $leftovers leftover files listed above; remove them by hand after review"
  removed=0
  for i in "${!dumps[@]}"; do
    name=${dumps[$i]}
    [ "$i" -lt "$KEEP" ] && continue
    [ "$name" = "$newest_verified" ] && continue
    base="$DIR/${name%.dump}"
    echo "  $name"
    if [ "$APPLY" = true ]; then
      rm -f -- "$base.dump" "$base.dump.sha256" "$base.fingerprint" "$base.verified"
    fi
    removed=$((removed + 1))
  done
  if [ "$APPLY" = true ]; then echo "PRUNE OK: $removed backup sets removed"
  else echo "PRUNE DRY RUN: $removed backup sets would be removed"; fi
  exit 0
fi

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
  coproc SNAP { $DOCKER exec -i -e PGTZ=UTC "$LIVE" psql -X -q -At -v ON_ERROR_STOP=1 -U argus_owner -d argus; }
  snap_read=${SNAP[0]}; snap_write=${SNAP[1]}; snap_pid=$SNAP_PID
  backup_cleanup() {
    if [ -n "${snap_write:-}" ]; then
      printf 'ROLLBACK;\n' 1>&"$snap_write" 2>/dev/null || true
      exec {snap_write}>&-
    fi
    if [ -n "${snap_pid:-}" ]; then wait "$snap_pid" 2>/dev/null || true; fi
    rm -f -- "$base.dump.part"
  }
  trap backup_cleanup EXIT
  printf 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\nSELECT pg_export_snapshot();\n' >&"$snap_write" \
    || stop "could not start a read-only snapshot"
  IFS= read -r snapshot <&"$snap_read" || stop "could not export a snapshot from $LIVE"
  [[ "$snapshot" =~ ^[0-9A-Fa-f-]+$ ]] || stop "invalid snapshot identifier from $LIVE"

  printf "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1;\nSELECT '__ARGUS_TABLES_DONE__';\n" \
    >&"$snap_write" || stop "could not list tables in the snapshot"
  tables=()
  tables_done=false
  while IFS= read -r t <&"$snap_read"; do
    if [ "$t" = __ARGUS_TABLES_DONE__ ]; then tables_done=true; break; fi
    [[ "$t" =~ ^[a-z_][a-z0-9_]*$ ]] || stop "unexpected table name in $LIVE"
    tables+=("$t")
  done
  [ "$tables_done" = true ] || stop "table list ended before its marker"
  [ "${#tables[@]}" -gt 0 ] || stop "no tables found in $LIVE (is it running?)"
  before=""
  for t in "${tables[@]}"; do
    printf '%s\n' "SELECT '$t ' || count(*) || ' ' || coalesce(md5(string_agg(x::text, E'\\n' ORDER BY x::text)), '-') FROM public.\"$t\" x;" \
      >&"$snap_write" || stop "could not fingerprint $t"
    IFS= read -r line <&"$snap_read" || stop "could not fingerprint $t"
    before+="$line"$'\n'
  done
  before=${before%$'\n'}
  $DOCKER exec "$LIVE" pg_dump -U argus_owner -d argus --snapshot="$snapshot" -Fc > "$base.dump.part" \
    || stop "pg_dump failed"
  printf 'COMMIT;\n' >&"$snap_write" || stop "could not end the snapshot"
  exec {snap_write}>&-
  snap_write=""
  wait "$snap_pid" || stop "snapshot session failed"
  snap_pid=""
  mv "$base.dump.part" "$base.dump"
  printf '%s\n' "$before" > "$base.fingerprint"
  (cd "$DIR" && sha256sum "$(basename "$base.dump")" > "$(basename "$base.dump").sha256")
  chmod 600 "$base.dump" "$base.fingerprint" "$base.dump.sha256"
  trap - EXIT
  echo "$before" | awk '{t++; r+=$2} END {print "  " t " tables, " r " rows"}'
  echo "BACKUP OK: $base.dump ($(wc -c < "$base.dump") bytes)"
  exit 0
fi

# --- verify ------------------------------------------------------------------------------------------------------
if [ "$DUMP" = latest ]; then              # found here, as root: the operator's shell cannot list the 700 folder
  DUMP=$(ls -1 "$DIR"/argus-*.dump 2>/dev/null | sort | tail -1 || true)
  [ -n "$DUMP" ] || stop "no dump in $DIR (run backup first)"
fi
echo "  dump: $DUMP"
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
printf 'verified_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${DUMP%.dump}.verified"
chmod 600 "${DUMP%.dump}.verified"
echo "$got" | awk '{t++; r+=$2} END {print "VERIFY OK: " t " tables, " r " rows match"}'
