"""T-0019 batch 3c: network verbs (ARCHITECTURE §4.6, §12.2) — why a container cannot reach another, and repeated TCP.

`network.connectivity` (Level 2, read gateway; decided 2026-10-12, `conantkd`, option A2): for a source and a
destination container of the same host's inventory, the networks of each side (names only) and the ones they share,
in one read. "No shared network" is the cause of SC-07 (T-0018), stated as a fact instead of left to the model to
infer from two statuses. DNS and TCP stay their own verbs. A combined capability (§12.7) was not built for one use.
`network.tcp_connect` (`check_tcp_connection`) takes `attempts` (1–5): an intermittent failure is told from a
permanent one, with each attempt's latency (§12.2's "repeated attempts + latency").
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from argus.capabilities.catalog import build_catalog
from argus.capabilities.spec import ExecutorError
from argus.detectors.classes import CLASSES
from argus.domain.model import TargetRef

ROOT = Path(__file__).resolve().parents[1]
CLIENT = TargetRef.parse("vm-166/container:argus-lab-client")
SPECS = {s.name: s for s in build_catalog()}


def _service(tmp_path, monkeypatch, role="read_gateway"):
    cfg = tmp_path / "target.json"
    cfg.write_text(json.dumps({"host": "vm-166", "containers": ["argus-lab-client", "argus-lab-backend", "argus-lab-api"],
                               "tcp": [["argus-lab-backend", 8080]]}), encoding="utf-8")
    monkeypatch.setenv("ROLE", "exporter")                # no token file needed; the route functions are module-level
    monkeypatch.setenv("TA_CONFIG", str(cfg))
    spec = importlib.util.spec_from_file_location(f"ta_service_3c_{role}", ROOT / "services" / "target" / "service.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NETS = {"argus-lab-client": {"argus-lab-app": {"IPAddress": "172.30.2.9"}},
        "argus-lab-backend": {"argus-lab-iso": {"IPAddress": "172.30.3.2"}},
        "argus-lab-api": {"argus-lab-app": {"IPAddress": "172.30.2.4"}, "argus-v18-mon": {"IPAddress": "172.30.1.7"}}}


def _docker(path):
    name = path.split("/")[2]
    return {"Id": "abc123def4567890", "State": {"Status": "running", "Running": True}, "HostConfig": {}, "Config": {},
            "NetworkSettings": {"Networks": NETS[name]}}


# --- read gateway: /connectivity ------------------------------------------------------------------------------------

def test_the_gateway_answers_the_networks_of_both_sides_and_the_shared_ones(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "djson", _docker)
    d = svc.read_gateway(["connectivity"], {"from": ["argus-lab-client"], "to": ["argus-lab-backend"]})
    assert d["from"]["networks"] == ["argus-lab-app"] and d["to"]["networks"] == ["argus-lab-iso"]
    assert d["shared"] == [] and d["from"]["running"] is True and d["to"]["name"] == "argus-lab-backend"
    d = svc.read_gateway(["connectivity"], {"from": ["argus-lab-client"], "to": ["argus-lab-api"]})
    assert d["shared"] == ["argus-lab-app"]
    assert "172.30." not in json.dumps(d)                                      # names only, never an address


@pytest.mark.parametrize("q,code", [({"from": ["argus-lab-client"], "to": ["argus-lab-other"]}, 404),   # not allowlisted
                                    ({"from": ["argus-lab-client"], "to": ["argus-lab-client"]}, 400),   # the same one
                                    ({"from": ["argus-lab-client"]}, 400)])
def test_the_gateway_refuses_a_pair_outside_its_allowlist(tmp_path, monkeypatch, q, code):
    svc = _service(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "djson", _docker)
    with pytest.raises(svc.Err) as e:
        svc.read_gateway(["connectivity"], q)
    assert e.value.code == code


# --- network probe: /tcp with attempts -------------------------------------------------------------------------------

def test_the_probe_repeats_a_tcp_connect_and_reports_each_attempt(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch, "network_probe")
    answers = iter([{"ok": True, "duration_ms": 2.0}, {"ok": False, "error": "TimeoutError: timed out",
                                                       "duration_ms": 3000.0}, {"ok": True, "duration_ms": 4.0}])
    monkeypatch.setattr(svc, "tcp", lambda host, port, timeout=3: next(answers))
    monkeypatch.setattr(svc.time, "sleep", lambda s: None)
    d = svc.network_probe(["tcp"], {"host": ["argus-lab-backend"], "port": ["8080"], "attempts": ["3"]})
    assert [a["ok"] for a in d["attempts"]] == [True, False, True] and d["succeeded"] == 2
    assert d["ok"] is False and d["duration_ms"] == 4.0                   # ok only when every attempt connected


def test_one_attempt_is_the_old_answer(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch, "network_probe")
    monkeypatch.setattr(svc, "tcp", lambda host, port, timeout=3: {"ok": True, "duration_ms": 1.5})
    d = svc.network_probe(["tcp"], {"host": ["argus-lab-backend"], "port": ["8080"]})
    assert d["ok"] is True and d["duration_ms"] == 1.5 and d["succeeded"] == 1 and len(d["attempts"]) == 1


@pytest.mark.parametrize("attempts", ["0", "6", "x"])
def test_the_probe_bounds_the_attempts(tmp_path, monkeypatch, attempts):
    svc = _service(tmp_path, monkeypatch, "network_probe")
    with pytest.raises(svc.Err) as e:
        svc.network_probe(["tcp"], {"host": ["argus-lab-backend"], "port": ["8080"], "attempts": [attempts]})
    assert e.value.code == 400


# --- capabilities ----------------------------------------------------------------------------------------------------

def test_connectivity_is_a_level_2_dependency_tool():
    s = SPECS["network.connectivity"]
    assert (s.model_name, s.level, s.safety_class, s.executor) == ("check_connectivity", 2, "READ_ONLY_SAFE", "docker_read")
    assert s.target_kinds == frozenset({"container"}) and s.tags == frozenset({"connectivity"})
    offered = [c.name for c in CLASSES if s.tags & c.tool_tags]
    assert offered == ["dependency_unavailable"]          # only the class whose cases answer it (6 evaluation cases)
    pol = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    assert pol["capabilities"]["network.connectivity"]["max_per_incident"] >= 2


class _Client:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return self.answer


def test_connectivity_says_when_two_containers_share_no_network():
    s = SPECS["network.connectivity"]
    c = _Client({"from": {"name": "argus-lab-client", "running": True, "networks": ["argus-lab-app"]},
                 "to": {"name": "argus-lab-backend", "running": True, "networks": ["argus-lab-iso"]},
                 "shared": [], "collected_at": "2026-10-12T19:00:00+00:00"})
    r = s.impl(s.args_model(to="argus-lab-backend"), CLIENT, None, c)
    assert c.calls == [("/connectivity", {"from": "argus-lab-client", "to": "argus-lab-backend"})]
    assert "NO shared network" in r.model_text and "argus-lab-iso" in r.model_text and "argus-lab-app" in r.model_text
    c.answer = {**c.answer, "shared": ["argus-lab-app"]}
    assert "shared networks: argus-lab-app" in s.impl(s.args_model(to="argus-lab-backend"), CLIENT, None, c).model_text


def test_connectivity_without_an_answer_is_unknown_not_isolated():
    s = SPECS["network.connectivity"]
    r = s.impl(s.args_model(to="argus-lab-backend"), CLIENT, None, _Client({"collected_at": None}))
    assert "unknown" in r.model_text and "NO shared network" not in r.model_text


def test_connectivity_refuses_itself_and_bad_names():
    s = SPECS["network.connectivity"]
    with pytest.raises(ExecutorError):
        s.impl(s.args_model(to="argus-lab-client"), CLIENT, None, _Client({}))
    for bad in ("../x", "a b", "", "x" * 200):
        with pytest.raises(Exception):
            s.args_model(to=bad)


def test_tcp_connect_takes_attempts():
    s = SPECS["network.tcp_connect"]
    assert s.args_model(port=8080).attempts == 1
    with pytest.raises(Exception):
        s.args_model(port=8080, attempts=6)
    info = type("I", (), {"tcp_ports": [8080]})()
    c = _Client({"ok": False, "succeeded": 2, "duration_ms": 4.0, "collected_at": None,
                 "attempts": [{"ok": True, "duration_ms": 2.0}, {"ok": False, "duration_ms": 3000.0, "error": "timeout"},
                              {"ok": True, "duration_ms": 4.0}]})
    r = s.impl(s.args_model(port=8080, attempts=3), TargetRef.parse("vm-166/container:argus-lab-backend"), info, c)
    assert c.calls == [("/tcp", {"host": "argus-lab-backend", "port": 8080, "attempts": 3})]
    assert "2/3 connected" in r.model_text and "3000" in r.model_text
    c1 = _Client({"ok": True, "duration_ms": 1.5, "collected_at": None})            # an old probe: no attempts key
    r = s.impl(s.args_model(port=8080), TargetRef.parse("vm-166/container:argus-lab-backend"), info, c1)
    assert c1.calls == [("/tcp", {"host": "argus-lab-backend", "port": 8080})] and "ok in 1.5 ms" in r.model_text


# --- evaluation cases ------------------------------------------------------------------------------------------------

def test_the_dependency_cases_answer_connectivity_from_their_own_statuses():
    """Each dependency case answers /connectivity for its source and every dependency, from its status fixtures."""
    cases = sorted((ROOT / "tests" / "eval" / "cases").glob("*.yaml"))
    seen = 0
    for p in cases:
        case = yaml.safe_load(p.read_text(encoding="utf-8"))
        if case["label"].get("class") != "dependency_unavailable":
            continue
        dr = (case.get("fixtures") or {}).get("docker_read") or {}
        keys = [k for k in dr if k.startswith("/connectivity?")]
        assert keys, p.name
        for k in keys:
            q = dict(x.split("=", 1) for x in k.split("?", 1)[1].split("&"))
            nets = {n: set((dr.get(f"/containers/{n}/status") or {}).get("networks") or []) for n in (q["from"], q["to"])}
            assert sorted(nets[q["from"]] & nets[q["to"]]) == dr[k]["shared"], (p.name, k)
            seen += 1
    assert seen >= 6
    wrong = yaml.safe_load((ROOT / "tests" / "eval" / "cases" / "dep-backend-wrong-network.yaml").read_text(encoding="utf-8"))
    assert any(v["shared"] == [] for k, v in wrong["fixtures"]["docker_read"].items() if k.startswith("/connectivity?"))


def test_attempts_to_a_port_that_never_answers_stay_under_the_clients_timeout(tmp_path, monkeypatch):
    """#101 review: 5 attempts x 3 s + 4 gaps would be 17 s, past the agent's 10 s client timeout (the read would end
    `timeout` and mark the network probe down for the whole incident). A shared 8 s budget stops the attempts."""
    svc = _service(tmp_path, monkeypatch, "network_probe")
    clock = {"t": 1000.0}
    waits = []

    def never(host, port, timeout=3):
        waits.append(timeout)
        clock["t"] += timeout                                  # a SYN nobody answers: the whole timeout
        return {"ok": False, "error": "TimeoutError: timed out", "duration_ms": timeout * 1000}
    monkeypatch.setattr(svc, "tcp", never)
    monkeypatch.setattr(svc.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(svc.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    d = svc.network_probe(["tcp"], {"host": ["argus-lab-backend"], "port": ["8080"], "attempts": ["5"]})
    assert clock["t"] - 1000.0 <= svc.TCP_BUDGET_S < 10                 # under the client's 10 s
    assert d["budget_exhausted"] is True and d["requested"] == 5 and len(d["attempts"]) < 5
    assert d["ok"] is False and d["succeeded"] == 0 and all(w <= 3 for w in waits)
    s = SPECS["network.tcp_connect"]
    info = type("I", (), {"tcp_ports": [8080]})()
    r = s.impl(s.args_model(port=8080, attempts=5), TargetRef.parse("vm-166/container:argus-lab-backend"), info,
               _Client(d))
    assert "time budget was spent" in r.model_text and "0/" in r.model_text
