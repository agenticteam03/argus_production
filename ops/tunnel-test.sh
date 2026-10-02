#!/usr/bin/env bash
# Run on VM 0.95 with sudo. Tests the restricted SSH tunnel to VM 0.166 WITHOUT any Argus service:
#   1. an ALLOWED forward reaches a temporary test listener on VM 0.166 127.0.0.1:18701  -> expect 200
#   2. a FORBIDDEN forward (to VM 0.166 port 22) is refused by the key's permitopen list -> expect 000
#   3. a shell/command is refused (nologin + restrict)                                    -> expect refusal
# Uses temporary loopback ports 28701 and 28022 on VM 0.95 only for the duration of the test.
set -u
HOSTS_ENV=${ARGUS_HOSTS_ENV:-/opt/argus-v18/hosts.env}   # VM-local, never committed (template: deploy/hosts.env.example)
[ -r "$HOSTS_ENV" ] && . "$HOSTS_ENV"
PEER="argus-v18-tunnel@${ARGUS_VM166_PRIVATE_IP:?missing: see $HOSTS_ENV}"
K=/opt/argus-v18/secrets/tunnel
SSH=(ssh -i "$K/id_ed25519" -o UserKnownHostsFile="$K/known_hosts" -o StrictHostKeyChecking=yes
     -o BatchMode=yes -o ConnectTimeout=10)

"${SSH[@]}" -o ExitOnForwardFailure=yes -N \
  -L 127.0.0.1:28701:127.0.0.1:18701 -L 127.0.0.1:28022:127.0.0.1:22 \
  "$PEER" 2>/tmp/argus-tunnel-test.err &
PID=$!
sleep 4
if ! kill -0 "$PID" 2>/dev/null; then
  echo "TUNNEL FAILED TO START:"; cat /tmp/argus-tunnel-test.err; rm -f /tmp/argus-tunnel-test.err; exit 1
fi
echo "1. allowed forward  (expect 200): $(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:28701/)"
echo "2. forbidden forward (expect 000): $(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:28022/)"
kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null
echo "3. shell attempt (expect refusal):"
"${SSH[@]}" "$PEER" id 2>&1 | tail -2
echo "--- ssh client messages during the test:"
grep -iE "prohibited|denied|refused|failed" /tmp/argus-tunnel-test.err | sort -u | head -5
rm -f /tmp/argus-tunnel-test.err
