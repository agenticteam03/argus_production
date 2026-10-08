#!/bin/sh
# T-0021 test only (tests/test_tool_isolation.py, ARGUS_TEST_DOCKER=1): runs as root in a throwaway agent container.
# Writes fake executor tokens owned by argus-tools (0400), as on vm-095, then runs the isolation check as the worker.
set -eu
python - <<'PY'
import os, pwd, yaml
inv = yaml.safe_load(open("/app/config/inventory.yaml"))
tools = pwd.getpwnam("argus-tools")
for host, h in inv["hosts"].items():
    os.makedirs(f"/run/argus-secrets/{host}", exist_ok=True)
    os.chmod(f"/run/argus-secrets/{host}", 0o755)
    for ex in h["executors"]:
        if ex == "prometheus":
            continue
        p = f"/run/argus-secrets/{host}/{ex}_token"
        open(p, "w").write("fake-token")
        os.chown(p, tools.pw_uid, tools.pw_gid)
        os.chmod(p, 0o400)
PY
exec setpriv --reuid=argus --regid=argus --init-groups python -m argus.tooling.isolation_check
