#!/usr/bin/env bash
# Scenario 2 reset, run ON vm-166 by the developer: the lab api returns to its own network. Lab names only.
# Refuses any host but argus-vm166. The isolated network is left in place (the SC-07 profile owns its removal).
set -euo pipefail

# Runs only on argus-vm166 (ARGUS_HOSTNAME replaces the host name in tests); argus-vm095 and any other host are refused.
HOST=${ARGUS_HOSTNAME:-$(hostname)}
if [ "$HOST" != "argus-vm166" ]; then
  echo "refused: this script runs only on argus-vm166, never on argus-vm095 or any other host" >&2
  exit 2
fi

APP=argus-lab-app
ISO=argus-lab-iso
API=argus-lab-api

docker network connect argus-lab-app argus-lab-api
docker network disconnect argus-lab-iso argus-lab-api
echo "s2-reset: $API back on $APP, off $ISO"
