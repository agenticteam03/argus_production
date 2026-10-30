"""T-0059 (ACR-0044): which inventory targets exist on their host, from the observers' presence series.

Every observer publishes, for each declared target it watches, `argus_target_present{kind,name}` (1 the target exists
on the host, 0 it does not) and `argus_target_up{kind,name}` (1 it runs). No series means the observer did not say:
unknown, never absent. The map and the target list read them through the named signals `target_present` and
`target_up`; the inventory stays the list of what may be investigated.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.outbound.config_adapters import PrometheusMetrics, YamlInventory
from argus.application.topology import Topology, presence
from argus.domain.model import TargetRef
from argus.infrastructure.wiring import read_signals
from test_core import FakeMetrics, make_app  # noqa: F401  (make_app is a fixture)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


# --- the exporter: containers ------------------------------------------------------------------------------------------
def _exporter(tmp_path, monkeypatch, containers=("argus-lab-worker",)):
    cfg = tmp_path / "target.json"
    cfg.write_text('{"host":"vm-166","containers":[%s]}' % ",".join(f'"{c}"' for c in containers), encoding="utf-8")
    monkeypatch.setenv("ROLE", "exporter")
    monkeypatch.setenv("TA_CONFIG", str(cfg))
    spec = importlib.util.spec_from_file_location("target_t0059", ROOT / "services/target/service.py")
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    monkeypatch.setattr(service.time, "sleep", lambda s: (_ for _ in ()).throw(StopIteration))
    monkeypatch.setattr(service, "container_events", lambda name, minutes: [])
    return service


def _collect(service) -> dict[str, str]:
    with pytest.raises(StopIteration):
        service.collect()
    return {ln.rsplit(" ", 1)[0]: ln.rsplit(" ", 1)[1] for ln in service._metrics.splitlines()
            if ln.startswith("argus_target_")}


def _state(running: bool) -> dict:
    return {"restart_count": 0, "created_at_seconds": None, "running": running, "restarting": False,
            "exit_code": 0 if running else 137, "oom_killed": False, "health": "none"}


def test_the_exporter_says_a_container_runs_or_is_stopped(tmp_path, monkeypatch):
    service = _exporter(tmp_path, monkeypatch, ("argus-lab-worker", "argus-lab-client"))
    monkeypatch.setattr(service, "inspect", lambda name: _state(name == "argus-lab-worker"))
    monkeypatch.setattr(service, "stats", lambda name, one_shot=False: {"memory_usage_bytes": None})
    lines = _collect(service)
    assert lines['argus_target_present{kind="container",name="argus-lab-worker"}'] == "1"
    assert lines['argus_target_up{kind="container",name="argus-lab-worker"}'] == "1"
    assert lines['argus_target_present{kind="container",name="argus-lab-client"}'] == "1"     # stopped, still there
    assert lines['argus_target_up{kind="container",name="argus-lab-client"}'] == "0"


def test_a_container_docker_does_not_know_is_absent_and_a_failed_read_says_nothing(tmp_path, monkeypatch):
    service = _exporter(tmp_path, monkeypatch, ("argus-lab-burner", "argus-lab-worker"))

    def inspect(name):
        if name == "argus-lab-burner":
            raise service.Err(404, "container not found on this host")
        raise OSError("the socket is gone")
    monkeypatch.setattr(service, "inspect", inspect)
    lines = _collect(service)
    assert lines['argus_target_present{kind="container",name="argus-lab-burner"}'] == "0"
    assert lines['argus_target_up{kind="container",name="argus-lab-burner"}'] == "0"
    assert not any("argus-lab-worker" in k for k in lines)          # unknown: no series, never absent


# --- the named signals --------------------------------------------------------------------------------------------------
def test_the_presence_signals_are_templates_on_kind_and_name(monkeypatch):
    signals = read_signals(ROOT / "config")
    assert signals["target_present"] == 'argus_target_present{argus_host="$host",kind="$kind",name="$name"}'
    assert signals["target_up"] == 'argus_target_up{argus_host="$host",kind="$kind",name="$name"}'
    inv = YamlInventory('hosts: {h1: {executors: {prometheus: "http://prom:9090"}}}\n'
                        'targets: [{ref: h1/service:cron.service}]\n')
    asked = []

    def get(url, params=None, timeout=None):
        asked.append(params["query"])
        return httpx.Response(200, json={"data": {"result": [{"value": [NOW.timestamp(), "1"]}]}},
                              request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setattr("time.time", lambda: NOW.timestamp())
    PrometheusMetrics(inv, {"target_up": signals["target_up"]}).snapshot(TargetRef.parse("h1/service:cron.service"),
                                                                          {"target_up"})
    assert asked == ['argus_target_up{argus_host="h1",kind="service",name="cron.service"}']


# --- presence and the map -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind,vals,expected", [
    ("container", {"target_present": 1, "target_up": 1}, "running"),
    ("container", {"target_present": 1, "target_up": 0}, "stopped"),
    ("container", {"target_present": 0, "target_up": 0}, "absent"),
    ("container", {"target_present": None, "target_up": None, "restarts_10m": 0}, "unknown"),
    ("container", {}, "unknown"),
    ("service", {"target_present": 1, "target_up": 0}, "stopped"),
    ("process", {"target_present": 1, "target_up": 1}, "running"),
    ("host", {"host_cpu_busy_ratio": 0.2}, "running"),
    ("host", {}, "unknown"),
    ("database", {}, "unknown"),
])
def test_presence_from_the_readings(kind, vals, expected):
    assert presence(kind, vals) == expected


INVENTORY = """
hosts:
  h1: {executors: {prometheus: "http://prom.internal:9090"}}
targets:
  - ref: h1/host:h1
  - ref: h1/container:web
  - ref: h1/container:client
  - ref: h1/container:burner
    profile: scenario
  - ref: h1/service:cron.service
  - ref: h1/process:backup
    process: {comm: backup.sh}
"""


class NoStore:
    def list_evidence(self, incident_id):
        return []

    def link_events_since(self, *a, **k):
        return []


def _topo(values):
    return Topology(YamlInventory(INVENTORY), FakeMetrics(values), NoStore(), now=lambda: NOW)


def test_the_map_shows_a_stopped_container_as_stopped_not_running():
    """Red before: a stopped container still publishes its restart count, so `restarts_10m` = 0 read as running."""
    body = _topo({"h1/container:client": {"restarts_10m": 0, "target_present": 1, "target_up": 0}}).view()
    box = next(n for n in body["nodes"] if n["id"] == "h1/container:client")
    assert box["status"] == "stopped" and box["health"] == "failed" and box["presence"] == "stopped"


def test_the_map_has_services_and_processes_with_their_state():
    body = _topo({"h1/service:cron.service": {"target_present": 1, "target_up": 1},
                  "h1/process:backup": {"target_present": 1, "target_up": 0}}).view()
    cron = next(n for n in body["nodes"] if n["id"] == "h1/service:cron.service")
    backup = next(n for n in body["nodes"] if n["id"] == "h1/process:backup")
    assert (cron["sub"], cron["status"], cron["health"]) == ("service", "running", "healthy")
    assert (backup["sub"], backup["status"], backup["health"]) == ("process", "stopped", "failed")


def test_an_absent_scenario_container_is_idle_on_the_map():
    body = _topo({"h1/container:burner": {"target_present": 0, "target_up": 0}}).view()
    box = next(n for n in body["nodes"] if n["id"] == "h1/container:burner")
    assert box["presence"] == "absent" and box["health"] == "idle"


def test_presences_by_target():
    t = _topo({"h1/container:web": {"target_present": 1, "target_up": 1},
               "h1/container:burner": {"target_present": 0, "target_up": 0}})
    states = t.presences()
    assert states["h1/container:web"] == "running" and states["h1/container:burner"] == "absent"
    assert states["h1/container:client"] == "unknown"


# --- the target list ----------------------------------------------------------------------------------------------------
def test_the_target_list_says_which_targets_exist(make_app):
    from argus.adapters.inbound.http import build_api
    app = make_app()
    some = sorted(str(t.ref) for t in app.inventory.targets() if t.ref.kind == "container")
    here, gone = some[0], some[1]
    app.topology.metrics = FakeMetrics({here: {"target_present": 1, "target_up": 1},
                                        gone: {"target_present": 0, "target_up": 0}})
    app.topology._global = None
    app.store.upsert_principal("vera", "human", "viewer", ["lab"], PasswordHash.recommended().hash("pw-123456789"))
    c = TestClient(build_api(app))
    tok = c.post("/api/v1/auth/token", data={"username": "vera", "password": "pw-123456789"}).json()["access_token"]
    rows = {r["target"]: r for r in c.get("/api/v1/targets", headers={"Authorization": f"Bearer {tok}"}).json()}
    assert set(rows[here]) == {"target", "host", "kind", "name", "state"}
    assert rows[here]["state"] == "running" and rows[gone]["state"] == "absent"
    assert {r["state"] for t, r in rows.items() if t not in (here, gone)} <= {"unknown", "running", "stopped"}
    assert set(rows) == {str(t.ref) for t in app.inventory.targets()}     # the inventory still decides the list


# --- step 2: Podman through its Docker-compatible socket ----------------------------------------------------------------
@pytest.mark.parametrize("path,service", [("deploy/target/compose.target.yml", "argus-v18-read-gateway"),
                                          ("deploy/target/compose.target.yml", "argus-v18-exporter"),
                                          ("deploy/target/compose.actions.yml", None)])
def test_the_container_runtime_socket_is_the_hosts_choice(path, service):
    """A host on Podman sets ARGUS_CONTAINER_SOCKET (its Docker-compatible API socket) in its env file; inside the
    container the path stays /var/run/docker.sock, so the read gateway, the exporter and the action gateway are the
    same code for both runtimes. Unset, it is Docker's socket."""
    import yaml
    compose = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))["services"]
    for name, svc in compose.items():
        if service not in (None, name):
            continue
        socket_mounts = [v for v in svc.get("volumes", []) if v.split(":")[-2 if v.count(":") > 1 else -1]
                         .startswith("/var/run/docker.sock")]
        if service is None and not socket_mounts:
            continue
        assert socket_mounts and all(v.startswith("${ARGUS_CONTAINER_SOCKET:-/var/run/docker.sock}:/var/run/docker.sock")
                                     for v in socket_mounts), (name, socket_mounts)


# --- step 3: systemd services and host processes, observed by the host probe -------------------------------------------
INV_UNITS = """
hosts:
  h1: {executors: {host_probe: "http://hp:8700"}}
targets:
  - ref: h1/host:h1
  - ref: h1/service:cron.service
  - ref: h1/process:backup
    process: {comm: backup.sh}
  - ref: h1/process:sync
    process: {pidfile: /run/argus-sync.pid}
"""


def test_the_inventory_accepts_services_and_processes_it_can_observe():
    inv = YamlInventory(INV_UNITS)
    assert {str(t.ref) for t in inv.targets()} >= {"h1/service:cron.service", "h1/process:backup", "h1/process:sync"}
    assert inv.target(TargetRef.parse("h1/process:backup")).process == {"comm": "backup.sh"}


@pytest.mark.parametrize("target,why", [
    ("{ref: h1/service:cron}", "must end in .service"),
    ("{ref: 'h1/service:a b.service'}", "must end in .service"),
    ("{ref: h1/process:x}", "exactly one of comm or pidfile"),
    ("{ref: h1/process:x, process: {comm: a, pidfile: /run/a.pid}}", "exactly one of comm or pidfile"),
    ("{ref: h1/process:x, process: {comm: a-name-longer-than-15}}", "at most 15"),
    ("{ref: h1/process:x, process: {pidfile: ../run/a.pid}}", "plain absolute path"),
    ("{ref: h1/container:x, process: {comm: a}}", "only a process target"),
])
def test_the_inventory_refuses_what_no_observer_can_read(target, why):
    with pytest.raises(ValueError, match=why):
        YamlInventory("hosts: {h1: {}}\ntargets: [%s]\n" % target)


def test_the_rendered_allowlist_names_the_hosts_services_and_processes():
    import yaml
    spec = importlib.util.spec_from_file_location("render_t0059", ROOT / "ops/render_target_config.py")
    render = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render)
    cfg = render.render_host(yaml.safe_load(INV_UNITS), "h1")
    assert cfg["services"] == ["cron.service"]
    assert cfg["processes"] == [{"name": "backup", "comm": "backup.sh"}, {"name": "sync", "pidfile": "/run/argus-sync.pid"}]


def _host_probe(tmp_path, monkeypatch):
    proc, rootfs, secrets = tmp_path / "proc", tmp_path / "rootfs", tmp_path / "secrets"
    for d in (proc, rootfs / "lib/systemd/system", rootfs / "run", secrets):
        d.mkdir(parents=True)
    (secrets / "host_probe_token").write_text("tok", encoding="utf-8")
    (rootfs / "lib/systemd/system/cron.service").write_text("[Unit]\n", encoding="utf-8")
    (rootfs / "lib/systemd/system/nginx.service").write_text("[Unit]\n", encoding="utf-8")

    def pid(n, comm, cgroup):
        (proc / str(n)).mkdir()
        (proc / str(n) / "stat").write_text(f"{n} ({comm}) S 1 0 0 0 0 0 0 0 0 0 1 1 0 0 20 0 1 0 1 1000 25\n",
                                            encoding="utf-8")
        (proc / str(n) / "comm").write_text(comm + "\n", encoding="utf-8")
        (proc / str(n) / "cgroup").write_text(cgroup, encoding="utf-8")
    pid(1, "systemd", "0::/init.scope\n")
    pid(410, "cron", "0::/system.slice/cron.service\n")
    pid(777, "backup.sh", "0::/user.slice/user-1000.slice/session-3.scope\n")
    (rootfs / "run/argus-sync.pid").write_text("999\n", encoding="utf-8")           # a stale pidfile: not running
    cfg = tmp_path / "target.json"
    cfg.write_text('{"host":"h1","services":["cron.service","nginx.service","gone.service"],'
                   '"processes":[{"name":"backup","comm":"backup.sh"},{"name":"sync","pidfile":"/run/argus-sync.pid"}]}',
                   encoding="utf-8")
    for k, v in {"ROLE": "host_probe", "TA_CONFIG": str(cfg), "TA_PROC": str(proc), "TA_ROOTFS": str(rootfs),
                 "TA_SECRETS": str(secrets)}.items():
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location("hp_t0059", ROOT / "services/target/service.py")
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    return service


def test_the_host_probe_says_which_services_and_processes_exist_and_run(tmp_path, monkeypatch):
    service = _host_probe(tmp_path, monkeypatch)
    lines = dict(ln.rsplit(" ", 1) for ln in service.unit_metrics().splitlines() if ln and not ln.startswith("#"))
    assert lines['argus_target_present{kind="service",name="cron.service"}'] == "1"
    assert lines['argus_target_up{kind="service",name="cron.service"}'] == "1"
    assert lines['argus_target_present{kind="service",name="nginx.service"}'] == "1"      # installed, not running
    assert lines['argus_target_up{kind="service",name="nginx.service"}'] == "0"
    assert lines['argus_target_present{kind="service",name="gone.service"}'] == "0"       # no unit file: absent
    assert lines['argus_target_up{kind="process",name="backup"}'] == "1"
    assert lines['argus_target_present{kind="process",name="sync"}'] == "1"              # declared: expected to run
    assert lines['argus_target_up{kind="process",name="sync"}'] == "0"


def test_the_host_probe_reads_one_service_or_process_and_nothing_else(tmp_path, monkeypatch):
    service = _host_probe(tmp_path, monkeypatch)
    cron = service.host_probe(["services", "cron.service", "status"], {})
    assert (cron["unit"], cron["installed"], cron["active"], cron["pids"]) == ("cron.service", True, True, [410])
    backup = service.host_probe(["processes", "backup", "status"], {})
    assert backup["running"] is True and backup["pids"] == [{"pid": 777, "command": "backup.sh", "state": "S",
                                                             "rss_mib": 0.1}]
    assert "cmdline" not in json.dumps(backup)
    sync = service.host_probe(["processes", "sync", "status"], {})
    assert sync["running"] is False and sync["match"] == {"pidfile": "/run/argus-sync.pid"} and sync["pids"] == []
    for parts in (["services", "ssh.service", "status"], ["processes", "other", "status"]):
        with pytest.raises(service.Err) as e:
            service.host_probe(parts, {})
        assert e.value.code == 404


def test_each_hosts_prometheus_scrapes_the_host_probe_with_its_token():
    import yaml
    for host in ("vm-095", "vm-166"):
        cfg = yaml.safe_load((ROOT / f"deploy/monitoring/prometheus-{host}.yml").read_text(encoding="utf-8"))
        job = next(j for j in cfg["scrape_configs"] if j["job_name"] == "argus-v18-host-probe")
        assert job["authorization"] == {"type": "Bearer", "credentials_file": "/etc/prometheus/secrets/host_probe_token"}
        assert job["static_configs"][0]["targets"] == ["argus-v18-host-probe:8700"]
        assert job["static_configs"][0]["labels"] == {"argus_host": host}
