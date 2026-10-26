#!/bin/sh
# Phase 19 exit proof (ACR-0019 §3.9; tests/test_phase19_real_images.py, ARGUS_TEST_DOCKER=1): runs as root in a
# throwaway agent container. Writes a fake action token where the worker would mount it (owned by argus, 0400, in the
# secrets folder owned by argus, 0501) and proves: the worker reads it; argus-tools (the MCP tools child) cannot, neither
# directly nor through sudo, whose only rule is the tools-server launcher without arguments.
set -eu
TOKEN=/run/argus-secrets/action_token
mkdir -p /run/argus-secrets
chown argus:argus /run/argus-secrets
chmod 0501 /run/argus-secrets
printf 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' > "$TOKEN"
chown argus:argus "$TOKEN"
chmod 0400 "$TOKEN"

fail() { echo "FAIL $1"; exit 1; }
setpriv --reuid=argus --regid=argus --init-groups cat "$TOKEN" >/dev/null 2>&1 || fail "the worker cannot read the token"
echo "ok   the worker (argus) reads the action token"
if setpriv --reuid=argus-tools --regid=argus-tools --init-groups cat "$TOKEN" >/dev/null 2>&1; then
    fail "argus-tools reads the action token"
fi
echo "ok   argus-tools cannot read the action token"
if setpriv --reuid=argus --regid=argus --init-groups sudo -n -u argus-tools /bin/cat "$TOKEN" >/dev/null 2>&1; then
    fail "the worker can make argus-tools read the token through sudo"
fi
echo "ok   sudo refuses argus-tools any command but the launcher"
if setpriv --reuid=argus --regid=argus --init-groups sudo -n -u argus-tools /usr/local/bin/argus-tools-server "$TOKEN" \
        >/dev/null 2>&1; then
    fail "the launcher accepts an argument"
fi
echo "ok   the launcher takes no argument"
echo "ACTION TOKEN ISOLATION OK"
