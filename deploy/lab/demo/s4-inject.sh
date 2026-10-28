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

# The fault goes through the worker's own HTTP endpoint (needs FAULT_ENABLE=1 in its environment). A marker file in the
# container would survive `docker restart`, so a restarted worker would stay frozen; the endpoint state is in memory.
# Both calls are idempotent: unfreeze on a worker that is not frozen still answers 200 and also removes a leftover marker.
if ! docker exec "$container" python -c 'import sys,urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080" + sys.argv[1], timeout=5).read().decode(), end="")' "/fault/$action"; then
  echo "could not set the fault on $container: it must be running with FAULT_ENABLE=1" >&2
  exit 1
fi
