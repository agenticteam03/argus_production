#!/usr/bin/env bash
# Scenario 2 injection, run ON vm-166 by the developer: the lab api leaves its network and joins the isolated one.
# Lab names only. Refuses vm-095. Undo with s2-reset.sh.
set -euo pipefail

if [ "$(hostname)" = "vm-095" ]; then
  echo "refused: this script never runs on vm-095" >&2
  exit 2
fi

APP=argus-lab-app
ISO=argus-lab-iso
API=argus-lab-api

docker network inspect "$ISO" >/dev/null 2>&1 || docker network create --subnet 172.30.3.0/24 "$ISO"
docker network disconnect argus-lab-app argus-lab-api
docker network connect argus-lab-iso argus-lab-api
echo "s2-inject: $API moved from $APP to $ISO"
