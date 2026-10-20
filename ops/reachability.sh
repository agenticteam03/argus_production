#!/usr/bin/env bash
# READ-ONLY cross-VM reachability test for the Argus v1.8 candidate ports. Changes nothing.
# It opens a short-lived listener-free TCP connection attempt to the peer's private IP per port.
#   open    = something answered
#   refused = the packet reached the peer (no listener / host reject) → the network path is OPEN
#   timeout = the packet was dropped on the way → FILTERED (most likely the Oracle VCN security list)
# Usage on each VM:  bash reachability.sh
set -u
HOSTS_ENV=${ARGUS_HOSTS_ENV:-/opt/argus-v18/hosts.env}   # VM-local, never committed (template: deploy/hosts.env.example)
# shellcheck source=/dev/null   # hosts.env exists only on the VMs
[ -r "$HOSTS_ENV" ] && . "$HOSTS_ENV"
: "${ARGUS_VM095_PRIVATE_IP:?missing: see $HOSTS_ENV}" "${ARGUS_VM166_PRIVATE_IP:?missing: see $HOSTS_ENV}"
case " $(hostname -I) " in
  *" $ARGUS_VM095_PRIVATE_IP "*) ME="VM 0.95"; PEER=$ARGUS_VM166_PRIVATE_IP;;
  *" $ARGUS_VM166_PRIVATE_IP "*) ME="VM 0.166"; PEER=$ARGUS_VM095_PRIVATE_IP;;
  *) echo "unknown machine"; exit 1;;
esac
echo "from $ME to $PEER  ($(date -u +%FT%TZ))"
for p in 22 18000 18001 18090 18093 18100 18180 18701 18702 18703 18704 18705; do
  start=$(date +%s%N)
  if timeout 4 bash -c "</dev/tcp/$PEER/$p" 2>/dev/null; then r=open; else rc=$?; [ "$rc" -eq 124 ] && r="timeout (filtered)" || r="refused (path open)"; fi
  printf '%-6s %-20s %5d ms\n' "$p" "$r" $(( ($(date +%s%N) - start) / 1000000 ))
done
