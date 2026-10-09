#!/bin/sh
# T-0021 test only (tests/test_tool_isolation.py, ARGUS_TEST_DOCKER=1): runs as root in a throwaway agent container.
# Writes fake executor tokens with vm-095's layout after T-0021 step 5: the secrets folder owned by argus, 0501 (others
# may only traverse it); each host folder owned by argus-tools, 0500; each token owned by argus-tools, 0400. Then runs
# the isolation check as the worker.
set -eu
python - <<'PY'
import os, pwd, yaml
inv = yaml.safe_load(open("/app/config/inventory.yaml"))
tools, worker = pwd.getpwnam("argus-tools"), pwd.getpwnam("argus")
os.makedirs("/run/argus-secrets", exist_ok=True)
os.chown("/run/argus-secrets", worker.pw_uid, worker.pw_gid)
os.chmod("/run/argus-secrets", 0o501)
for host, h in inv["hosts"].items():
    os.makedirs(f"/run/argus-secrets/{host}", exist_ok=True)
    os.chown(f"/run/argus-secrets/{host}", tools.pw_uid, tools.pw_gid)
    os.chmod(f"/run/argus-secrets/{host}", 0o500)
    for ex in h["executors"]:
        if ex == "prometheus":
            continue
        p = f"/run/argus-secrets/{host}/{ex}_token"
        open(p, "w").write("fake-token")
        os.chown(p, tools.pw_uid, tools.pw_gid)
        os.chmod(p, 0o400)
PY
exec setpriv --reuid=argus --regid=argus --init-groups python -m argus.tooling.isolation_check
