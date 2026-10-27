#!/usr/bin/env bash
# Scenario 2 reset, run ON vm-166 by the developer: the lab api returns to its own network. Lab names only.
# Refuses vm-095. The isolated network is left in place (the SC-07 profile owns its removal).
set -euo pipefail

if [ "$(hostname)" = "vm-095" ]; then
  echo "refused: this script never runs on vm-095" >&2
  exit 2
fi

APP=argus-lab-app
ISO=argus-lab-iso
API=argus-lab-api

docker network connect argus-lab-app argus-lab-api
docker network disconnect argus-lab-iso argus-lab-api
echo "s2-reset: $API back on $APP, off $ISO"
