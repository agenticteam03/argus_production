#!/bin/sh
set -eu

usage() {
    echo "usage: s1-reset.sh argus-lab-CONTAINER" >&2
    exit 2
}

require_vm166() {
    host=$(hostname)
    if [ "$host" != "vm-166" ]; then
        echo "refusing to reset outside vm-166" >&2
        exit 1
    fi
}

require_lab_container() {
    case "$1" in
        argus-lab-*) suffix=${1#argus-lab-} ;;
        *) echo "refusing non-lab container name" >&2; exit 1 ;;
    esac
    case "$suffix" in
        ""|*[!A-Za-z0-9_.-]*) echo "refusing invalid lab container name" >&2; exit 1 ;;
    esac
}

[ "$#" -eq 1 ] || usage
container=$1
require_lab_container "$container"
require_vm166

docker start "$container"
attempt=0
while [ "$attempt" -lt 60 ]; do
    if docker exec argus-lab-api python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2)' >/dev/null 2>&1; then
        exit 0
    fi
    sleep 1
    attempt=$((attempt + 1))
done

echo "api did not become healthy within 60 seconds" >&2
exit 1
