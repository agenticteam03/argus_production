#!/bin/sh
# T-0033 (Phase 13): rotate ONE executor token of THIS host's target service. The token is never printed.
#   sudo sh /opt/argus-v18/app/ops/rotate-token.sh <docker_read|host_probe|network_probe> --as <developer>
#   sudo sh /opt/argus-v18/app/ops/rotate-token.sh <executor> --rollback --as <developer>   (back to <file>.prev)
# A new random token replaces /opt/argus-v18/secrets/<executor>_token (same owner and mode; the old one is kept as
# <executor>_token.prev, mode 0400, until the next rotation), then that ONE service is recreated so it reads it (the
# service reads its token at start). The agent's copy on vm-095 (/opt/argus-v18/secrets/agent/<host>/) is replaced
# separately; the agent re-reads it on its next rejected read, without a restart (argus/tooling/dispatch.py).
# db_probe is not rotated here: this host's Prometheus scrapes it with the same token (its scrape config too).
# A rollback keeps the live file's owner and mode; a failed recreate exits 1 and says how to roll back (#94 review).
# Tests: ARGUS_DEPLOY_HOME, ARGUS_DOCKER and ARGUS_HOSTNAME replace /opt/argus-v18, docker and the host name.
set -eu
HOME_DIR=${ARGUS_DEPLOY_HOME:-/opt/argus-v18}
DOCKER=${ARGUS_DOCKER:-docker}
HOST=${ARGUS_HOSTNAME:-$(hostname)}
EX=${1:-}
MODE=rotate
[ "${2:-}" = "--rollback" ] && { MODE=rollback; shift; }
[ "${2:-}" = "--as" ] && [ -n "${3:-}" ] || { echo "usage: rotate-token.sh <executor> [--rollback] --as <developer>"; exit 2; }
WHO=$3
case $EX in
  docker_read)   SVC=argus-v18-read-gateway ;;
  host_probe)    SVC=argus-v18-host-probe ;;
  network_probe) SVC=argus-v18-network-probe ;;
  *) echo "executor must be docker_read, host_probe or network_probe (db_probe: see the header)"; exit 2 ;;
esac
F=$HOME_DIR/secrets/${EX}_token
[ -f "$F" ] || { echo "no $F: nothing to rotate"; exit 1; }
case $(echo "$HOST" | sed 's/^argus-//') in
  vm095) V=vm-095; O=compose.core-join.yml ;;
  vm166) V=vm-166; O=compose.loopback.yml ;;
  *) echo "unknown host $HOST"; exit 1 ;;
esac

if [ "$MODE" = rollback ]; then
  [ -f "$F.prev" ] || { echo "no $F.prev: nothing to roll back to"; exit 1; }
  # the old content, with the LIVE file's owner and mode (not .prev's 0400): the service may read it through its group
  NEW=$(mktemp "$HOME_DIR/secrets/.${EX}_token.XXXXXX")
  cat "$F.prev" >"$NEW"
  chown --reference="$F" "$NEW"
  chmod --reference="$F" "$NEW"
  mv "$NEW" "$F"
else
  NEW=$(mktemp "$HOME_DIR/secrets/.${EX}_token.XXXXXX")
  tr -dc 'A-Za-z0-9_-' </dev/urandom | head -c 43 >"$NEW"
  [ "$(wc -c <"$NEW")" -eq 43 ] || { rm -f "$NEW"; echo "token generation failed"; exit 1; }
  chown --reference="$F" "$NEW"
  chmod --reference="$F" "$NEW"
  cp -p "$F" "$F.prev"
  chmod 0400 "$F.prev"
  mv "$NEW" "$F"
fi

cd "$HOME_DIR/app/deploy/target"
UP=$(echo "$MODE" | tr a-z A-Z)
if ! OUT=$("$DOCKER" compose --env-file "$V.env" -f compose.target.yml -f "$O" up -d --force-recreate --no-deps "$SVC" \
           </dev/null 2>&1); then
  echo "$OUT" | tail -5
  echo "TOKEN $UP $EX on $V by $WHO FAILED: the token file changed but $SVC was NOT recreated (it still holds the" \
       "previous token). Fix the error and run the compose command again, or: rotate-token.sh $EX --rollback --as $WHO"
  exit 1
fi
echo "$OUT" | grep -E 'Recreated|Started' || true
echo "TOKEN $UP $EX on $V by $WHO: $SVC recreated; sha256 $(sha256sum "$F" | cut -c1-12)" \
  "(the token itself is not printed)"
