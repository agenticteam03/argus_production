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

# Safe to run twice, and after Argus itself restored the network: each step runs only when it is needed.
attached=" $(docker inspect -f '{{range $name, $net := .NetworkSettings.Networks}}{{$name}} {{end}}' "$API") "

if [[ "$attached" == *" $APP "* ]]; then
  echo "s2-reset: $API is already on $APP, connect skipped"
else
  docker network connect argus-lab-app argus-lab-api
  echo "s2-reset: $API connected to $APP"
fi
if [[ "$attached" == *" $ISO "* ]]; then
  docker network disconnect argus-lab-iso argus-lab-api
  echo "s2-reset: $API disconnected from $ISO"
else
  echo "s2-reset: $API is not on $ISO, disconnect skipped"
fi
echo "s2-reset: $API back on $APP, off $ISO"
