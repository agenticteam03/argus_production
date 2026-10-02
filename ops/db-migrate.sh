#!/usr/bin/env bash
# Apply deploy/migrations/*.sql to argus-v18-postgres as the owner: in order, each exactly once, each in ONE
# transaction; a migration whose file changed after it was applied is refused. Then set argus_runtime's password from
# the agent's secret (sent on stdin, never on a command line). Run on vm-095:  sudo bash ops/db-migrate.sh
set -euo pipefail
C=${ARGUS_PG_CONTAINER:-argus-v18-postgres}
DIR=${ARGUS_MIGRATIONS:-$(cd "$(dirname "$0")/../deploy/migrations" && pwd)}
PWFILE=${ARGUS_DB_PASSWORD_FILE:-/opt/argus-v18/secrets/agent/db_password}
pg() { docker exec -i -e PGOPTIONS="-c client_min_messages=warning" "$C" psql -X -q -v ON_ERROR_STOP=1 -U argus_owner -d argus "$@"; }

pg -c "CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, sha256 text NOT NULL,
       applied_at timestamptz NOT NULL DEFAULT now())"
for f in "$DIR"/*.sql; do
  v=$(basename "$f" .sql); h=$(sha256sum "$f" | cut -c1-64)
  applied=$(pg -At -c "SELECT sha256 FROM schema_migrations WHERE version = '$v'")
  if [ -n "$applied" ]; then
    [ "$applied" = "$h" ] || { echo "REFUSED: migration $v changed after it was applied"; exit 1; }
    echo "  = $v (already applied)"; continue
  fi
  { echo "BEGIN;"; cat "$f"; echo "INSERT INTO schema_migrations (version, sha256) VALUES ('$v', '$h');"; echo "COMMIT;"; } | pg
  echo "  + $v applied"
done
[ -s "$PWFILE" ] || { echo "missing $PWFILE"; exit 1; }
{ printf "\set pw '%s'\n" "$(cat "$PWFILE")"; echo "ALTER ROLE argus_runtime PASSWORD :'pw';"; } | pg
echo "  argus_runtime password set"
pg -At -c "SELECT 'schema: ' || string_agg(version, ', ' ORDER BY version) FROM schema_migrations"
