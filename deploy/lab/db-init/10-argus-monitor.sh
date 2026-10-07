#!/bin/sh
# argus-lab-db (TESTING ONLY, T-0019): the read-only monitoring role used by argus-v18-db-probe.
# pg_monitor only: it reads pg_stat_activity / pg_locks / pg_settings and no table. Runs once, on an empty data
# directory (tmpfs: every container start). The password comes from a file and is never printed.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v pw="$(cat /run/secrets/monitor_password)" <<'SQL'
CREATE ROLE argus_monitor LOGIN PASSWORD :'pw' CONNECTION LIMIT 3;
GRANT pg_monitor TO argus_monitor;
SQL
