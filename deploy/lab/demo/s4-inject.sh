#!/bin/sh
set -eu

action=${1:-}
case "$action" in
  freeze|unfreeze) ;;
  *) echo "usage: $0 freeze|unfreeze" >&2; exit 2 ;;
esac

host=$(hostname)
case "$host" in
  *vm-095*|*vm095*) echo "refusing to run on vm-095" >&2; exit 1 ;;
esac

container=argus-lab-jobworker
case "$container" in
  argus-lab-*) ;;
  *) echo "refusing non-lab container" >&2; exit 1 ;;
esac

if [ "$action" = freeze ]; then
  docker exec "$container" touch /tmp/freeze
else
  docker exec "$container" rm -f /tmp/freeze
fi
