#!/bin/sh
# ACR-0011 (T-0016 step 4e): host rules for the public UI edge, in Docker's DOCKER-USER chain, because a port that
# Docker publishes is DNAT-ed to the container and never traverses INPUT (whose REJECT protects only host services).
#   sudo sh /opt/argus-v18/app/ops/ui-firewall.sh apply --as <developer>    add the rules (idempotent)
#   sudo sh /opt/argus-v18/app/ops/ui-firewall.sh remove --as <developer>   remove them (the rollback)
#   sudo sh /opt/argus-v18/app/ops/ui-firewall.sh status                    list them (read-only)
# What they do: at most 50 open connections per client address to the edge's ports (443, 80), the rest dropped.
# Reachability itself is the published ports (only argus-v18-ui publishes 443/80) and the cloud rule. Every rule
# carries the comment "argus-v18-ui"; nothing else in DOCKER-USER, and no other chain, is touched (the protected
# wg0 rules included). nonint-check excludes Docker's chains, so these rules do not appear in its snapshot.
set -eu
IPT=${ARGUS_IPTABLES:-iptables}
HOME_DIR=${ARGUS_DEPLOY_HOME:-/opt/argus-v18}
TAG=argus-v18-ui
CMD=${1:-}
WHO=""
[ "${2:-}" = "--as" ] && WHO=${3:-}
rule() {   # $1 = -C / -I / -D, $2 = port
  "$IPT" "$1" DOCKER-USER -p tcp -m conntrack --ctstate NEW --ctorigdstport "$2" \
    -m connlimit --connlimit-above 50 --connlimit-mask 32 -m comment --comment "$TAG" -j DROP
}
need_session() {
  [ -n "$WHO" ] || { echo "$CMD needs --as <developer>"; exit 2; }
  grep -q "^holder=$WHO " "$HOME_DIR/SESSION" 2>/dev/null || { echo "NOT YOUR SESSION - stop here"; exit 1; }
}
case "$CMD" in
  status)
    "$IPT" -S DOCKER-USER | grep -- "--comment $TAG" || echo "no $TAG rules" ;;
  apply)
    need_session
    for p in 443 80; do rule -C "$p" 2>/dev/null || rule -I "$p"; done
    echo "UI FIREWALL APPLIED: $("$IPT" -S DOCKER-USER | grep -c -- "--comment $TAG") rules ($TAG)" ;;
  remove)
    need_session
    for p in 443 80; do while rule -C "$p" 2>/dev/null; do rule -D "$p"; done; done
    echo "UI FIREWALL REMOVED: $("$IPT" -S DOCKER-USER | grep -c -- "--comment $TAG" || true) rules left ($TAG)" ;;
  *)
    echo "usage: ui-firewall.sh apply|remove --as <developer> | status"; exit 2 ;;
esac
