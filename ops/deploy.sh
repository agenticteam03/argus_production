#!/usr/bin/env bash
# Put an exact commit of argus_production on this VM (shared-Brain plan, deploy method B). Run with sudo:
#   sudo bash /opt/argus-v18/app/ops/deploy.sh <branch|commit> --as <github-handle>     deploy a commit
#   sudo bash deploy.sh init <branch|commit> --as <github-handle>                       first time: turn app/ into a clone
#   sudo bash /opt/argus-v18/app/ops/deploy.sh status                                    what is deployed (read-only)
# It never restarts anything: it prints which services to rebuild. It refuses if /opt/argus-v18/SESSION is not
# yours, if the checkout has local modifications, or if the ref is unknown. Every run ends with a verdict line:
#   DEPLOY OK: <commit> (<ref>) on <host>      or      DEPLOY STOP: <reason>
# Fetching uses the VM's read-only deploy key in /opt/argus-v18/secrets/deploy/ (GitHub host key pinned there).
set -u
HOME_DIR="${ARGUS_DEPLOY_HOME:-/opt/argus-v18}"
REPO="${ARGUS_DEPLOY_REPO:-git@github.com:agenticteam03/argus_production.git}"
APP="$HOME_DIR/app"
KEYDIR="$HOME_DIR/secrets/deploy"

stop() { echo "DEPLOY STOP: $*"; exit 1; }

MODE=deploy REF="" WHO="${ARGUS_DEVELOPER:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    init|status) MODE="$1" ;;
    --as) shift; WHO="${1:-}" ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) [ -z "$REF" ] && REF="$1" || stop "unexpected argument '$1'" ;;
  esac
  shift
done

if [ -f "$KEYDIR/id_ed25519" ]; then
  export GIT_SSH_COMMAND="ssh -i $KEYDIR/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=$KEYDIR/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes"
fi
g() { git -C "$APP" -c safe.directory="$APP" "$@"; }

if [ "$MODE" = status ]; then
  cat "$HOME_DIR/DEPLOYED" 2>/dev/null || echo "(no DEPLOYED marker yet)"
  if g rev-parse --git-dir >/dev/null 2>&1; then
    echo "checkout: $(g rev-parse HEAD)  local modifications: $(g status --porcelain | wc -l)"
  else
    echo "checkout: $APP is not a git clone yet"
  fi
  D="${ARGUS_DOCKER:-docker}"
  # T-0014: the Argus programs on this host (vm-095: agent = api, worker, scheduler), with the command each one runs.
  $D ps -a --filter name=argus-v18- --format '{{.Names}} {{.State}} {{.Command}}' 2>/dev/null \
    | grep -E '^argus-v18-(agent|worker|scheduler) ' | sed 's/^/argus: /'
  # Is the lab at its baseline (every argus-lab-* running, none unhealthy)? A scenario left half-done makes the
  # next --check say DIAGNOSED (DEPLOY-MAIN found argus-lab-cache stopped for ~7 h); nonint-check ignores Argus objects.
  if ! LAB="$($D ps -a --filter name=argus-lab- --format '{{.Names}} {{.State}} {{.Status}}' 2>/dev/null)"; then
    echo "lab: docker not available"
  elif [ -z "$LAB" ]; then
    echo "lab: no argus-lab-* containers"
  else
    BAD=""
    while read -r name state rest; do
      echo "lab: $name $state $rest"
      if [ "$state" != running ] || echo "$rest" | grep -qE 'unhealthy|health: starting'; then BAD="$BAD $name"; fi
    done <<< "$LAB"
    [ -z "$BAD" ] && echo "LAB BASELINE OK" \
      || echo "LAB BASELINE NOT OK:$BAD (a scenario left the lab changed? restore it before testing)"
  fi
  exit 0
fi

[ -n "$REF" ] || stop "no branch or commit given (usage: deploy.sh [init] <branch|commit> --as <github-handle>)"
[ -n "$WHO" ] || stop "who are you? add --as <github-handle>"
grep -q "^holder=$WHO " "$HOME_DIR/SESSION" 2>/dev/null \
  || stop "NOT YOUR SESSION: /opt/argus-v18/SESSION says '$(head -c 80 "$HOME_DIR/SESSION" 2>/dev/null)' (claim it with brain.py start)"

PREV=""
[ -f "$HOME_DIR/DEPLOYED" ] && PREV="$(sed -n 's/^commit=//p' "$HOME_DIR/DEPLOYED")"

if [ "$MODE" = init ]; then
  g rev-parse --git-dir >/dev/null 2>&1 && stop "$APP is already a git clone (use deploy.sh <ref> without init)"
  KEPT=""
  if [ -e "$APP" ]; then
    KEPT="$APP.pre-git-$(date -u +%Y%m%dT%H%M%SZ)"
    mv "$APP" "$KEPT" || stop "could not move $APP aside"
    echo "kept the previous folder as $KEPT (rollback: move it back)"
  fi
  git clone --quiet "$REPO" "$APP" || { [ -n "$KEPT" ] && mv "$KEPT" "$APP"; stop "clone failed (deploy key? network?)"; }
else
  g rev-parse --git-dir >/dev/null 2>&1 || stop "$APP is not a git clone yet (run deploy.sh init <ref> first)"
  [ -z "$(g status --porcelain)" ] || stop "local modifications in $APP - nobody edits code on the VM (see: git -C $APP status)"
  g fetch --quiet --prune origin || stop "fetch failed (deploy key? network?)"
fi

SHA="$(g rev-parse --verify --quiet "origin/$REF^{commit}" || g rev-parse --verify --quiet "$REF^{commit}")" \
  || stop "unknown branch or commit '$REF'"
g checkout --quiet --detach "$SHA" || stop "checkout of $SHA failed"
[ -z "$(g status --porcelain)" ] || stop "checkout of $SHA left modifications"

printf 'commit=%s\nref=%s\ndeveloper=%s\ndeployed_at=%s\nprevious=%s\nhost=%s\n' \
  "$SHA" "$REF" "$WHO" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PREV" "$(hostname)" > "$HOME_DIR/DEPLOYED"

echo "Changed since the previous deployment:"
if [ -n "$PREV" ] && g cat-file -e "$PREV^{commit}" 2>/dev/null; then
  CHANGED="$(g diff --name-only "$PREV" "$SHA")"
else
  CHANGED="$(g ls-files)"
  echo "  (no previous commit known: treating every file as changed)"
fi
hint() { echo "$CHANGED" | grep -qE "$1" && echo "  - $2"; }
echo "Rebuild what changed (NOT done by this script; wrap it in nonint-check before/after):"
hint '^(argus/|Dockerfile|pyproject\.toml|deploy/vm-095/)' "agent, worker, scheduler (vm-095, one image; migrations first): cd $APP/deploy/vm-095 && sudo docker compose --env-file $HOME_DIR/hosts.env -f compose.core.yml up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler"
hint '^deploy/migrations/' "database migrations (vm-095): sudo bash $APP/ops/db-migrate.sh"
hint '^(services/target/|deploy/target/)' "target services: cd $APP/deploy/target && sudo docker compose --env-file <vm>.env -f compose.target.yml -f <compose.loopback.yml|compose.core-join.yml> up -d --build"
hint '^deploy/monitoring/' "monitoring: cd $APP/deploy/monitoring && sudo docker compose --env-file <vm>.env -f compose.monitoring.yml -f <compose.loopback.yml|compose.core-join.yml> up -d"
hint '^config/' "config (read at start): restart argus-v18-agent argus-v18-worker argus-v18-scheduler after reviewing the change"
hint '^deploy/scheduler/' "schedules (read at start): sudo docker restart argus-v18-scheduler after reviewing the change"
echo "DEPLOY OK: ${SHA:0:12} ($REF) on $(hostname)"
