"""Phase 19 exit proofs on real images (NEXT-PHASE plan; ACR-0019 §3.9, §4). Run with ARGUS_TEST_DOCKER=1 (CI sets it).

1. The MCP tools child cannot read the action token: in the agent image, the token where the worker mounts it is
   readable by `argus` only; `argus-tools` cannot read it, directly or through sudo.
2. The action gateway and the socket proxy, built from `services/action_gateway/Dockerfile`, run as two containers:
   only the proxy mounts Docker's socket; the gateway reaches it through the proxy's Unix socket, accepts only the
   released `(capability, target)` pair with its token and action id, journals it, refuses a duplicate, records
   Docker's 304 as `confirmed`, and the proxy refuses any unreleased Docker path.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid

import pytest

from test_core import ROOT

pytestmark = pytest.mark.skipif(os.getenv("ARGUS_TEST_DOCKER") != "1" or shutil.which("docker") is None,
                                reason="ARGUS_TEST_DOCKER=1 not set (needs Docker)")

TOKEN = "a" * 40                     # low entropy on purpose: a fake secret


def docker(*args: str, check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=check, capture_output=True, text=True, timeout=timeout)


def test_the_tools_child_cannot_read_the_action_token():
    tag = "argus-v18-agent:phase19-test"
    docker("build", "-q", "-t", tag, str(ROOT), timeout=900)
    script = ROOT / "deploy" / "agent" / "action-token-isolation-test.sh"
    r = docker("run", "--rm", "--user", "root", "-v", f"{script}:/check.sh:ro", tag, "sh", "/check.sh", check=False)
    assert r.stdout.strip().splitlines()[-1] == "ACTION TOKEN ISOLATION OK", r.stdout + r.stderr


def _post(port: int, path: str, action_id: str, body: dict, token: str = TOKEN) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method="POST", headers={
        "Authorization": f"Bearer {token}", "X-Argus-Action-Id": action_id, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def _get(port: int, path: str) -> tuple[int, dict]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def test_the_gateway_and_socket_proxy_on_real_images(tmp_path):
    run = uuid.uuid4().hex[:8]
    tag, volume = f"argus-v18-action-gateway:phase19-{run}", f"argus-p19-run-{run}"
    target, other = f"argus-lab-p19-{run}", f"argus-lab-p19-other-{run}"
    proxy, gateway = f"argus-p19-proxy-{run}", f"argus-p19-gateway-{run}"
    config = tmp_path / "action-gateway.json"
    config.write_text(json.dumps({"host": "vm-166", "released": [{
        "capability": "container.start", "target": f"vm-166/container:{target}",
        "route": f"POST /containers/{target}/start"}]}), encoding="utf-8")
    token = tmp_path / "action_token"
    token.write_text(TOKEN, encoding="utf-8")
    try:
        docker("build", "-q", "-f", str(ROOT / "services" / "action_gateway" / "Dockerfile"), "-t", tag, str(ROOT),
               timeout=900)
        for name in (target, other):
            docker("create", "--name", name, "python:3.12-alpine", "sleep", "600")
        sock_gid = docker("run", "--rm", "-v", "/var/run/docker.sock:/s", "python:3.12-alpine",
                          "stat", "-c", "%g", "/s").stdout.strip()
        docker("volume", "create", volume)
        docker("run", "-d", "--name", proxy, "--read-only", "--group-add", sock_gid, "-e", "ARGUS_ACTION_ROLE=proxy",
               "-v", "/var/run/docker.sock:/var/run/docker.sock", "-v", f"{volume}:/run/argus-v18",
               "-v", f"{config}:/etc/argus-v18/action-gateway.json:ro", tag)
        docker("run", "-d", "--name", gateway, "--read-only", "-e", "ARGUS_ACTION_ROLE=gateway",
               "-p", "127.0.0.1::8705", "-v", f"{volume}:/run/argus-v18",
               "-v", f"{token}:/run/argus-v18/action_token:ro",
               "--tmpfs", "/var/lib/argus-v18:uid=65532,gid=65532",
               "-v", f"{config}:/etc/argus-v18/action-gateway.json:ro", tag)
        port = int(docker("port", gateway, "8705").stdout.strip().splitlines()[0].rsplit(":", 1)[1])
        for _ in range(60):
            try:
                if _get(port, "/actions/act_" + "0" * 32)[0] in (403, 404):
                    break
            except OSError:                       # the published port answers before the listener is up
                pass
            time.sleep(0.5)
        else:
            pytest.fail(docker("logs", gateway, check=False).stderr + docker("logs", proxy, check=False).stderr)

        # Only the proxy has Docker's socket.
        assert docker("exec", gateway, "test", "-e", "/var/run/docker.sock", check=False).returncode != 0
        assert docker("exec", proxy, "test", "-S", "/var/run/docker.sock", check=False).returncode == 0

        identity = {"container_id": docker("inspect", "-f", "{{.Id}}", target).stdout.strip()}
        body = {"capability": "container.start", "target": f"vm-166/container:{target}", "target_identity": identity}
        first, second = "act_" + "1" * 32, "act_" + "2" * 32
        path = f"/containers/{target}/start"
        assert _post(port, path, first, body, token="b" * 40)[0] == 403                      # wrong token
        assert _post(port, f"/containers/{other}/start", first,
                     {**body, "target": f"vm-166/container:{other}"})[0] == 403             # not released
        assert _post(port, "/images/create", first, body)[0] == 404                          # not a container route
        assert _post(port, path, first, {**body, "target_identity": {"container_id": "x"}})[0] == 403
        assert docker("inspect", "-f", "{{.State.Running}}", target).stdout.strip() == "false"

        assert _post(port, path, first, body) == (200, {"status": "confirmed"})
        assert docker("inspect", "-f", "{{.State.Running}}", target).stdout.strip() == "true"
        assert _post(port, path, first, body)[0] == 409                                      # never twice
        assert _get(port, f"/actions/{first}") == (200, {"status": "confirmed"})
        assert _post(port, path, second, body) == (200, {"status": "confirmed"})            # Docker's 304

        # The worker's client (argus/actions/gateway_client.py) against the real gateway: the frozen proposal's route.
        from datetime import datetime, timezone
        from argus.actions.gateway_client import HttpActionGateway
        from argus.actions.remediation import freeze_proposal
        from test_phase18_remediation import candidate
        client = HttpActionGateway(f"http://127.0.0.1:{port}", token)
        proposal = freeze_proposal(candidate(target=f"vm-166/container:{target}", root_cause=f"vm-166/container:{target}",
                                             target_identity=identity), at=datetime.now(timezone.utc))
        third = "act_" + "3" * 32
        assert client.dispatch(third, proposal) == "confirmed" and client.status(third) == "confirmed"

        # The proxy refuses any Docker path that is not released, even from the gateway's own socket.
        probe = ("from services.action_gateway.unix_transport import UnixRequester as U;"
                 "r=U('/run/argus-v18/action-proxy.sock');"
                 f"print(r('GET','/containers/{other}/json')[0], r('GET','/containers/json')[0],"
                 f" r('POST','/containers/{other}/start', {{'X-Argus-Action-Id':'{first}'}})[0])")
        assert docker("exec", gateway, "python", "-c", probe).stdout.split() == ["403", "403", "403"]
        assert docker("inspect", "-f", "{{.State.Running}}", other).stdout.strip() == "false"
    finally:
        for name in (gateway, proxy, target, other):
            docker("rm", "-f", "-v", name, check=False)
        docker("volume", "rm", "-f", volume, check=False)
        docker("rmi", "-f", tag, check=False)
