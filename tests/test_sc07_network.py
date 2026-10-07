"""T-0018 / SC-07: a healthy backend on the wrong Docker network (vm-166).

Argus must be able to see which networks a container is attached to (read gateway + capability text), the
inventory must declare the client→backend dependency so the existing dependency probe fires, and the lab profile
must put the two containers on different networks inside the Argus address ranges.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _target_service(tmp_path, monkeypatch):
    cfg = tmp_path / "target.json"
    cfg.write_bytes(b'{"host": "vm-166", "containers": ["argus-lab-backend"]}')
    monkeypatch.setenv("ROLE", "exporter")            # no token file needed; inspect() is the same for every role
    monkeypatch.setenv("TA_CONFIG", str(cfg))
    return _load("ta_service_sc07", ROOT / "services" / "target" / "service.py")


def test_gateway_status_lists_the_attached_networks(tmp_path, monkeypatch):
    svc = _target_service(tmp_path, monkeypatch)
    raw = {"Id": "abc123def4567890", "State": {"Status": "running", "Running": True, "Health": {"Status": "healthy"}},
           "HostConfig": {}, "Config": {"Image": "python:3.12-alpine"},
           "NetworkSettings": {"Networks": {"argus-lab-iso": {"IPAddress": "172.30.3.2"}}}}
    monkeypatch.setattr(svc, "djson", lambda path: raw)
    d = svc.inspect("argus-lab-backend")
    assert d["networks"] == ["argus-lab-iso"]                  # names only: no addresses leave the gateway
    assert "172.30.3.2" not in json.dumps(d)


def test_gateway_status_without_networks_is_an_empty_list(tmp_path, monkeypatch):
    svc = _target_service(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "djson", lambda path: {"State": {}, "HostConfig": {}, "Config": {}})
    assert svc.inspect("argus-lab-backend")["networks"] == []


def test_container_status_shows_the_networks_to_the_model():
    from argus.capabilities.catalog import NoArgs, container_status
    from argus.domain.model import TargetRef

    class Client:
        def get(self, path):
            return {"id": "abc123def456", "state": "running", "health": "healthy", "restart_count": 0,
                    "networks": ["argus-lab-app", "argus-v18-mon"], "collected_at": "2026-10-06T20:00:00+00:00"}
    r = container_status(NoArgs(), TargetRef.parse("vm-166/container:argus-lab-client"), None, Client())
    assert "networks=argus-lab-app,argus-v18-mon" in r.model_text


def test_inventory_renders_the_sc07_dependency_probe(tmp_path, monkeypatch):
    """The rendered vm-166 allowlist must match the inventory (one source) and probe client→backend on TCP 8080."""
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "config" / "inventory.yaml", tmp_path / "config" / "inventory.yaml")
    render = _load("render_sc07", ROOT / "ops" / "render_target_config.py")
    monkeypatch.setattr(render, "ROOT", tmp_path)
    render.main()
    for host in ("vm-095", "vm-166"):
        rendered = (tmp_path / "deploy" / "target" / "config" / f"{host}.json").read_bytes()
        assert rendered == (ROOT / "deploy" / "target" / "config" / f"{host}.json").read_bytes(), f"{host}.json is stale"
    cfg = json.loads((ROOT / "deploy" / "target" / "config" / "vm-166.json").read_text(encoding="utf-8"))
    assert {"owner": "argus-lab-client", "dependency": "argus-lab-backend",
            "host": "argus-lab-backend", "port": 8080} in cfg["probes"]
    assert {"argus-lab-client", "argus-lab-backend"} <= set(cfg["containers"])


def test_lab_profile_puts_client_and_backend_on_different_networks():
    lab = yaml.safe_load((ROOT / "deploy" / "lab" / "compose.lab.yml").read_text(encoding="utf-8"))
    sc07 = {s["container_name"]: s for s in lab["services"].values() if "sc07" in s.get("profiles", [])}
    assert set(sc07) == {"argus-lab-client", "argus-lab-backend"}
    assert sc07["argus-lab-client"]["networks"] == ["argus-lab-app"]
    assert sc07["argus-lab-backend"]["networks"] == ["argus-lab-iso"]
    for s in sc07.values():                                    # hard limits, no published ports
        assert s.get("mem_limit") and s.get("cpus") and s.get("pids_limit") and "ports" not in s
    iso = lab["networks"]["argus-lab-iso"]
    assert iso["name"] == "argus-lab-iso" and not iso.get("external")
    assert iso["ipam"]["config"] == [{"subnet": "172.30.3.0/24"}]    # inside the Argus ranges (environment.md §3)


def test_exporter_probes_a_dependency_only_while_its_owner_runs(tmp_path, monkeypatch):
    """Outside SC-07 the client does not exist: its probe must not report 0 (DependencyProbeFailed would fire forever)."""
    svc = _target_service(tmp_path, monkeypatch)
    probes = [{"owner": "argus-lab-api", "dependency": "argus-lab-cache", "host": "argus-lab-cache", "port": 6379},
              {"owner": "argus-lab-client", "dependency": "argus-lab-backend", "host": "argus-lab-backend", "port": 8080}]
    monkeypatch.setattr(svc, "tcp", lambda host, port: {"ok": host == "argus-lab-cache", "duration_ms": 1.0})
    lines = svc.probe_lines(probes, active={"argus-lab-api"})
    assert 'argus_probe_success{owner="argus-lab-api",dependency="argus-lab-cache"} 1' in lines
    assert not any("argus-lab-client" in ln for ln in lines)
    lines = svc.probe_lines(probes, active={"argus-lab-api", "argus-lab-client"})
    assert 'argus_probe_success{owner="argus-lab-client",dependency="argus-lab-backend"} 0' in lines


def test_exporter_keeps_the_probe_of_an_owner_in_a_restart_loop(tmp_path, monkeypatch):
    """OP-007: an app that crash-loops because its dependency is down spends most samples in Docker's `restarting`
    state; its probe (the real cause) must stay published. A missing or stopped owner still has none."""
    svc = _target_service(tmp_path, monkeypatch)
    state = {"argus-lab-api": {"running": False, "restarting": True},       # crash loop: waiting to restart
             "argus-lab-client": {"running": False, "restarting": False}}   # stopped by design (SC-07 over)
    assert svc.owner_active(state["argus-lab-api"]) and not svc.owner_active(state["argus-lab-client"])
    assert svc.owner_active({"running": True, "restarting": False})
    probes = [{"owner": "argus-lab-api", "dependency": "argus-lab-cache", "host": "argus-lab-cache", "port": 6379},
              {"owner": "argus-lab-client", "dependency": "argus-lab-backend", "host": "argus-lab-backend", "port": 8080}]
    monkeypatch.setattr(svc, "tcp", lambda host, port: {"ok": False, "duration_ms": 1.0})
    active = {n for n, d in state.items() if svc.owner_active(d)}
    lines = svc.probe_lines(probes, active)
    assert 'argus_probe_success{owner="argus-lab-api",dependency="argus-lab-cache"} 0' in lines
    assert not any("argus-lab-client" in ln for ln in lines)


def test_container_status_tool_tells_the_model_it_returns_networks():
    """SC-07 runs 2-3: the model never compared both sides' networks; the tool description did not say it has them."""
    from argus.capabilities.catalog import build_catalog
    spec = next(s for s in build_catalog() if s.name == "container.status")
    assert "network" in spec.description.lower()
    assert "network" in spec.use_when.lower()
