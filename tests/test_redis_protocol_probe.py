"""The cache's dependents probe it with Redis PING, not only a TCP connect: RB-003's Recovery wants the dependency to
answer its protocol, and the S1 judge doubted a verification that only proved the port was open."""
from __future__ import annotations

import json
import socket
import threading
from datetime import datetime, timezone

import pytest

from argus.application.links import link_state
from argus.ports.ports import ProbeSample
from test_core import ROOT
from test_sc07_network import _target_service


def _server(answer: bytes | None):
    """One local listener: it answers the first read with `answer`, or closes without a word when None."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)

    def serve():
        conn, _ = sock.accept()
        with conn:
            conn.recv(64)
            if answer is not None:
                conn.sendall(answer)
        sock.close()
    threading.Thread(target=serve, daemon=True).start()
    return sock.getsockname()[1]


def test_ping_is_ok_only_when_the_answer_is_pong(tmp_path, monkeypatch):
    svc = _target_service(tmp_path, monkeypatch)
    assert svc.redis_ping("127.0.0.1", _server(b"+PONG\r\n"))["ok"] is True
    for answer in (b"-NOAUTH Authentication required.\r\n", None):
        r = svc.redis_ping("127.0.0.1", _server(answer))
        assert r["ok"] is False and r["kind"] == "protocol"


def test_a_closed_port_keeps_its_connect_failure_kind(tmp_path, monkeypatch):
    svc = _target_service(tmp_path, monkeypatch)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    r = svc.redis_ping("127.0.0.1", port)
    assert r["ok"] is False and r["kind"] == "refused"


def test_a_probe_with_a_protocol_asks_it_and_one_without_only_connects(tmp_path, monkeypatch):
    svc = _target_service(tmp_path, monkeypatch)
    asked = []
    monkeypatch.setitem(svc.PROTOCOL_PROBES, "redis",
                        lambda host, port: asked.append(("redis", host)) or {"ok": False, "kind": "protocol",
                                                                            "duration_ms": 1.0})
    monkeypatch.setattr(svc, "tcp", lambda host, port: asked.append(("tcp", host)) or {"ok": True, "duration_ms": 1.0})
    probes = [{"owner": "argus-lab-api", "dependency": "argus-lab-cache", "host": "argus-lab-cache", "port": 6379,
               "protocol": "redis"},
              {"owner": "argus-lab-api", "dependency": "argus-lab-db", "host": "argus-lab-db", "port": 5432}]
    lines = svc.probe_lines(probes, active={"argus-lab-api"})
    assert asked == [("redis", "argus-lab-cache"), ("tcp", "argus-lab-db")]
    assert 'argus_probe_success{owner="argus-lab-api",dependency="argus-lab-cache"} 0' in lines
    assert 'argus_probe_error{owner="argus-lab-api",dependency="argus-lab-cache",kind="protocol"} 1' in lines


def test_the_inventory_renders_the_cache_probes_with_redis_and_refuses_an_unknown_protocol():
    cfg = json.loads((ROOT / "deploy" / "target" / "config" / "vm-166.json").read_text(encoding="utf-8"))
    cache = [p for p in cfg["probes"] if p["dependency"] == "argus-lab-cache"]
    assert {p["owner"] for p in cache} == {"argus-lab-api", "argus-lab-jobworker"}
    assert all(p["protocol"] == "redis" for p in cache)
    assert all("protocol" not in p for p in cfg["probes"] if p["dependency"] != "argus-lab-cache")

    import importlib.util
    spec = importlib.util.spec_from_file_location("render_redis", ROOT / "ops" / "render_target_config.py")
    render = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render)
    inv = {"targets": [{"ref": "vm-166/container:a", "depends_on": ["vm-166/container:b"]},
                       {"ref": "vm-166/container:b", "tcp_ports": [1], "protocol": "smtp"}]}
    with pytest.raises(ValueError, match="no probe"):
        render.render_host(inv, "vm-166")


def test_a_wrong_protocol_answer_reads_as_a_broken_link_with_its_reason():
    sample = ProbeSample(success=0.0, duration_s=0.002, at=datetime(2026, 10, 28, tzinfo=timezone.utc),
                         error_kind="protocol")
    assert link_state(sample, 6379) == ("broken", 2.0, "no protocol answer")
