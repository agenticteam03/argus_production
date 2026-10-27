#!/bin/sh
set -eu

usage() {
    echo "usage: s1-inject.sh argus-lab-CONTAINER [cpu SECONDS]" >&2
    exit 2
}

require_vm166() {
    host=$(hostname)
    if [ "$host" != "vm-166" ]; then
        echo "refusing to inject outside vm-166" >&2
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

[ "$#" -ge 1 ] && [ "$#" -le 3 ] || usage
container=$1
fault=${2:-}
require_lab_container "$container"
require_vm166

case "$fault" in
    "") [ "$#" -eq 1 ] || usage ;;
    cpu)
        [ "$#" -eq 3 ] || usage
        seconds=$3
        case "$seconds" in
            ""|*[!0-9]*) usage ;;
        esac
        [ "$seconds" -ge 1 ] && [ "$seconds" -le 120 ] || usage
        ;;
    *) usage ;;
esac

docker stop "$container"
if [ "$fault" = "cpu" ]; then
    docker exec argus-lab-api python -c 'import sys,urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/fault/cpu?s=" + sys.argv[1], timeout=5).read().decode(), end="")' "$seconds"
fi
