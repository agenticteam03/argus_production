"""Phase 20 (X-3): the action gateway and its socket proxy as vm-166 services, and the one path to them from vm-095.

Defined, never started: no deploy command, env file or script loads `deploy/target/compose.actions.yml`, so the
standing write-gate check stays closed until the first release PR's window starts both with the token and the config.
The real-image proofs (two containers, only the proxy on Docker's socket, the token unreadable by `argus-tools`) stay
in `tests/test_phase19_real_images.py`.
"""
from __future__ import annotations

import re
import socket
import subprocess
from pathlib import Path

import pytest
import yaml

from argus.infrastructure.gate_report import ACTION_GATEWAY
from services.action_gateway import run

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = yaml.safe_load((ROOT / "deploy" / "target" / "compose.actions.yml").read_text(encoding="utf-8"))
CORE = yaml.safe_load((ROOT / "deploy" / "vm-095" / "compose.core.yml").read_text(encoding="utf-8"))
TUNNEL = (ROOT / "deploy" / "vm-095" / "tunnel" / "Dockerfile").read_text(encoding="utf-8")
PROXY, GATEWAY = "argus-v18-action-proxy", "argus-v18-action-gateway"
SOCKET_MOUNT = "/var/run/docker.sock:/var/run/docker.sock"


def _services(path):
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8")).get("services", {})


def test_two_services_one_image_hardened_and_never_root():
    services = ACTIONS["services"]
    assert set(services) == {PROXY, GATEWAY}
    assert ACTIONS["name"] == "argus-v18-actions"
    for name, spec in services.items():
        assert spec["container_name"] == name
        assert spec["image"] == "argus-v18-action-gateway:1"
        assert spec["build"] == {"context": "../..", "dockerfile": "services/action_gateway/Dockerfile"}
        assert spec["user"] == "65532:65532" and spec["read_only"] is True
        assert spec["cap_drop"] == ["ALL"] and spec["security_opt"] == ["no-new-privileges:true"]
        assert "privileged" not in spec
    assert services[PROXY]["environment"] == {"ARGUS_ACTION_ROLE": "proxy"}
    assert services[GATEWAY]["environment"] == {"ARGUS_ACTION_ROLE": "gateway"}


def test_only_the_proxy_mounts_docker_and_it_has_no_network():
    proxy, gateway = ACTIONS["services"][PROXY], ACTIONS["services"][GATEWAY]
    assert SOCKET_MOUNT in proxy["volumes"]
    assert proxy["network_mode"] == "none" and "ports" not in proxy
    assert proxy["group_add"][0].startswith("${ARGUS_DOCKER_GID:?")     # the socket's group, read on the VM
    assert not any("docker.sock" in v for v in gateway["volumes"])
    assert "group_add" not in gateway


def test_the_gateway_holds_the_token_and_journal_and_listens_on_loopback_only():
    proxy, gateway = ACTIONS["services"][PROXY], ACTIONS["services"][GATEWAY]
    assert gateway["ports"] == ["127.0.0.1:18705:8705"]
    assert "/opt/argus-v18/secrets/action/action_token:/run/argus-v18/action_token:ro" in gateway["volumes"]
    assert "argus-v18-action-journal:/var/lib/argus-v18" in gateway["volumes"]
    assert not any("action_token" in v or "journal" in v for v in proxy["volumes"])
    config = "/etc/argus-v18/action-gateway.json:/etc/argus-v18/action-gateway.json:ro"
    assert config in proxy["volumes"] and config in gateway["volumes"]
    assert "argus-v18-action-run:/run/argus-v18" in proxy["volumes"]       # the proxy's Unix socket, shared
    assert "argus-v18-action-run:/run/argus-v18" in gateway["volumes"]
    assert not any("candidate" in v for spec in ACTIONS["services"].values() for v in spec["volumes"])


def test_nothing_loads_the_actions_file_and_no_other_compose_file_has_an_action_service():
    for path in ROOT.glob("deploy/**/compose*.yml"):
        if path.name != "compose.actions.yml":
            assert not any("action" in name for name in _services(path.relative_to(ROOT))), path
    tracked = subprocess.run(["git", "ls-files", "ops", "deploy", ".claude/skills"], cwd=ROOT, check=True,
                             capture_output=True, text=True).stdout.split()
    for name in tracked:
        if name.endswith((".sh", ".env", ".py", ".service", ".timer")):
            assert "compose.actions" not in (ROOT / name).read_text(encoding="utf-8"), name


def test_the_tunnel_forwards_the_gateway_on_the_worker_only_network():
    forwards = re.findall(r'"-L", "([^"]+)"', TUNNEL)
    assert [f for f in forwards if f.endswith(":18705")] == ["172.30.5.2:18705:127.0.0.1:18705"]
    assert all(f.startswith("0.0.0.0:") for f in forwards if not f.endswith(":18705"))
    services, networks = CORE["services"], CORE["networks"]
    assert services["argus-v18-tunnel"]["networks"]["argus-v18-action"] == {"ipv4_address": "172.30.5.2"}
    assert networks["argus-v18-action"]["internal"] is True
    assert networks["argus-v18-action"]["ipam"]["config"] == [{"subnet": "172.30.5.0/24"}]
    members = {name for name, spec in services.items() if "argus-v18-action" in spec.get("networks", [])}
    assert members == {"argus-v18-tunnel", "argus-v18-worker"}


def test_the_gateway_name_still_resolves_nowhere_on_vm_095():
    """The write-gate check reports CLOSED only while ACTION_GATEWAY does not resolve; no alias gives it out early."""
    assert ACTION_GATEWAY not in CORE["services"]
    for name, spec in CORE["services"].items():
        nets = spec.get("networks", [])
        for net in nets.values() if isinstance(nets, dict) else []:
            assert ACTION_GATEWAY not in (net or {}).get("aliases", []), name


unix_only = pytest.mark.skipif(not hasattr(socket, "AF_UNIX") or not hasattr(socket, "SOCK_STREAM"),
                               reason="Unix sockets")


@unix_only
def test_the_proxy_replaces_a_stale_socket_left_by_a_restart(tmp_path):
    path = str(tmp_path / "proxy.sock")
    old = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old.bind(path)
    old.close()                                         # the file stays, nobody answers: the earlier run is gone
    run.clear_stale_socket(path)
    assert not Path(path).exists()


@unix_only
def test_the_proxy_still_refuses_a_live_socket_or_a_plain_file(tmp_path):
    path = str(tmp_path / "proxy.sock")
    live = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    live.bind(path)
    live.listen(1)
    try:
        with pytest.raises(RuntimeError, match="already exists"):
            run.clear_stale_socket(path)
    finally:
        live.close()
    plain = tmp_path / "plain"
    plain.write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not a socket"):
        run.clear_stale_socket(str(plain))
    run.clear_stale_socket(str(tmp_path / "absent"))    # nothing there: nothing to do
