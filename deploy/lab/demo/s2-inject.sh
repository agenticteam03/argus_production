#!/usr/bin/env bash
# Scenario 2 injection, run ON vm-166 by the developer: the lab api leaves its network and joins the isolated one.
# Lab names only. Refuses any host but argus-vm166. Undo with s2-reset.sh.
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

# the client whose link to the api is verified runs WITHOUT argus-lab-backend (profile sc07-api; SC-07 stays as it was)
LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docker compose -f "$LAB_DIR/compose.lab.yml" --profile sc07-api up -d argus-lab-client

docker network inspect "$ISO" >/dev/null 2>&1 || docker network create --subnet 172.30.3.0/24 "$ISO"
docker network disconnect argus-lab-app argus-lab-api
docker network connect argus-lab-iso argus-lab-api
echo "s2-inject: $API moved from $APP to $ISO"
