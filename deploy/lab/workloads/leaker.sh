#!/bin/sh
# SC-04 (T-0020): a defective worker that leaks database sessions. It opens $SESSIONS sessions on argus-lab-db as the
# ordinary role, starts a transaction in each and never ends it ("idle in transaction"), so the connection slots stay
# taken until the container stops (`compose --profile sc04 down` closes them). The password is read from a file and
# never printed. Connection settings come from PGHOST / PGDATABASE / PGUSER / PGAPPNAME.
set -eu
PGPASSWORD="$(cat /run/secrets/app_password)"
export PGPASSWORD
n=${SESSIONS:-16}
i=1
while [ "$i" -le "$n" ]; do
  ( printf 'BEGIN;\nSELECT 1;\n'; sleep 86400 ) | psql -q -X -v ON_ERROR_STOP=1 >/dev/null 2>&1 &
  i=$((i + 1))
  sleep 1
done
echo "leaker: opened $n sessions on $PGHOST/$PGDATABASE as $PGUSER, each idle in transaction"
wait
