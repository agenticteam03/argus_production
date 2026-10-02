#!/usr/bin/env bash
# Non-interference snapshot (read-only toward everything that is NOT Argus v1.8).
#   sudo bash nonint-check.sh before      → saves /opt/argus-v18/baseline/before.txt
#   sudo bash nonint-check.sh after       → saves after.txt and diffs it with before.txt
# Covers: containers + state, networks, volumes, listening ports, iptables rules outside Docker's own
# chains, network interfaces (incl. the pre-existing WireGuard wg0). Argus objects (argus-v18-*, argus-lab-*) are excluded.
set -u
LABEL="${1:?before|after|<label>}"
D=/opt/argus-v18/baseline
mkdir -p "$D"
OUT="$D/$LABEL.txt"
{
  echo "## containers (non-Argus)"
  docker ps -a --format '{{.Names}} {{.State}} {{.Image}}' | grep -vE '^argus-(v18|lab)-' \
    | sed -E 's/ restarting / running /' | sort
  echo "## networks (non-Argus)"
  docker network ls --format '{{.Name}}' | grep -vE '^argus-(v18|lab)-' | sort
  echo "## volumes (non-Argus)"
  for v in $(docker volume ls -q); do
    proj=$(docker volume inspect -f '{{index .Labels "com.docker.compose.project"}}' "$v" 2>/dev/null)
    case "$v $proj" in argus-v18*|*" argus-v18"*|*" argus-lab"*) ;; *) echo "$v";; esac
  done | sort
  echo "## listening TCP/UDP (excluding Argus ports)"
  ss -tulnH | awk '{print $1, $5}' | grep -vE ':(18000|1870[0-9]|18090)$' | sort -u
  echo "## iptables (outside Docker-managed chains)"
  iptables -S | grep -vE '^-[AN] DOCKER' | sort
  echo "## interfaces (excluding veth/bridges)"
  ip -brief link | awk '{print $1}' | grep -vE '^(veth|br-)' | sort
  echo "## wireguard interfaces"
  (command -v wg >/dev/null && wg show interfaces) || ip -brief link show type wireguard 2>/dev/null | awk '{print $1}'
} > "$OUT"
echo "saved $OUT ($(wc -l < "$OUT") lines)"
if [ "$LABEL" != "before" ] && [ -f "$D/before.txt" ]; then
  if diff "$D/before.txt" "$OUT"; then echo "NO INTERFERENCE: non-Argus objects unchanged"; else echo "DIFFERENCES ABOVE (< before, > now)"; fi
fi
