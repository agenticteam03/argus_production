"""T-0037: the Level 2 `docker_read` verbs of ARCHITECTURE §12 that were missing (read gateway + capabilities).

- `get_container_processes` (`container.processes`, `/containers/{name}/top`): PID, PPID and the command's NAME only,
  never its arguments (a command line can carry a password; `host.process_details` keeps the same rule).
- `get_docker_disk_usage` (`docker.disk_usage`, `/docker/df`): `/system/df` reduced to totals; no image, container or
  volume name.
- `get_detailed_logs` (`container.detailed_logs`): a time window (1–120 min), up to 500 lines, stdout / stderr / both.
- `search_logs` (`container.search_logs`): one of a FIXED set of named patterns (never free text, never a regex from
  the model) over a window: how many lines matched and up to 50 of them.
Every route is an exact GET on this host's allowlisted containers; offered to no class until measured.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from argus.capabilities.catalog import build_catalog
from argus.detectors.classes import CLASSES
from argus.domain.model import TargetRef

ROOT = Path(__file__).resolve().parents[1]
API = TargetRef.parse("vm-166/container:argus-lab-api")
HOST = TargetRef.parse("vm-166/host:vm-166")
SPECS = {s.name: s for s in build_catalog()}
NEW = {"container.processes": ("get_container_processes", {"container"}),
       "docker.disk_usage": ("get_docker_disk_usage", {"host"}),
       "container.detailed_logs": ("get_detailed_logs", {"container"}),
       "container.search_logs": ("search_logs", {"container"})}


def _service(tmp_path, monkeypatch):
    cfg = tmp_path / "target.json"
    cfg.write_text(json.dumps({"host": "vm-166", "containers": ["argus-lab-api"]}), encoding="utf-8")
    monkeypatch.setenv("ROLE", "exporter")
    monkeypatch.setenv("TA_CONFIG", str(cfg))
    spec = importlib.util.spec_from_file_location("ta_service_t0037", ROOT / "services" / "target" / "service.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _frames(lines: list[tuple[int, str]]) -> bytes:
    """Docker's multiplexed log stream: 1 = stdout, 2 = stderr."""
    out = b""
    for stream, text in lines:
        body = (text + "\n").encode()
        out += bytes([stream, 0, 0, 0]) + len(body).to_bytes(4, "big") + body
    return out


TOP = {"Titles": ["UID", "PID", "PPID", "C", "STIME", "TTY", "TIME", "CMD"],
       "Processes": [["root", "4242", "4200", "0", "10:00", "?", "00:00:01",
                      "python /app/server.py --db-password=hunter2 --port 8080"],
                     ["root", "4250", "4242", "0", "10:00", "?", "00:00:00", "/usr/bin/gunicorn -w 2"],
                     ["999", "4260", "4242", "0", "10:00", "?", "00:00:00", "postgres: checkpointer"]]}
DF = {"LayersSize": 2_000_000_000,
      "Images": [{"Id": "sha256:aaa", "RepoTags": ["argus-lab-api:1"], "Size": 150_000_000, "SharedSize": 0,
                  "Containers": 1},
                 {"Id": "sha256:bbb", "RepoTags": ["old:0"], "Size": 300_000_000, "SharedSize": 0, "Containers": 0}],
      "Containers": [{"Id": "c1", "Names": ["/argus-lab-api"], "SizeRw": 5_000_000, "State": "running"},
                     {"Id": "c2", "Names": ["/stopped-job"], "SizeRw": 1_000_000, "State": "exited"}],
      "Volumes": [{"Name": "pgdata", "UsageData": {"Size": 800_000_000, "RefCount": 1}},
                  {"Name": "orphan", "UsageData": {"Size": 50_000_000, "RefCount": 0}}],
      "BuildCache": [{"Size": 10_000_000, "InUse": False}]}
LOGS = _frames([(1, "2026-10-13T00:00:01Z GET /health 200"), (2, "2026-10-13T00:00:02Z ERROR db timeout after 5s"),
                (1, "2026-10-13T00:00:03Z GET /health 200"), (2, "2026-10-13T00:00:04Z connection refused by cache"),
                (2, "2026-10-13T00:00:05Z Traceback (most recent call last):")])


def _fake_docker(calls):
    def docker(path, timeout=10):
        calls.append(path)
        if path.endswith("/json") and path.startswith("/containers/"):
            return 200, json.dumps({"Config": {"Tty": False}, "State": {}, "HostConfig": {}}).encode()
        if "/top" in path:
            return 200, json.dumps(TOP).encode()
        if path.startswith("/system/df"):
            return 200, json.dumps(DF).encode()
        if "/logs" in path:
            return 200, LOGS
        return 404, b""
    return docker


# --- the gateway -------------------------------------------------------------------------------------------------------
def test_processes_are_pid_ppid_and_command_name_never_the_arguments(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "docker", _fake_docker([]))
    d = svc.read_gateway(["containers", "argus-lab-api", "top"], {})
    assert d["processes"] == [{"pid": 4242, "ppid": 4200, "command": "python"},
                              {"pid": 4250, "ppid": 4242, "command": "gunicorn"},
                              {"pid": 4260, "ppid": 4242, "command": "postgres"}]
    assert "hunter2" not in json.dumps(d) and "/app/server.py" not in json.dumps(d) and d["count"] == 3


def test_disk_usage_is_totals_only(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "docker", _fake_docker([]))
    d = svc.read_gateway(["docker", "df"], {})
    assert d["images"] == {"count": 2, "bytes": 450_000_000, "unused_count": 1, "unused_bytes": 300_000_000}
    assert d["containers"] == {"count": 2, "writable_bytes": 6_000_000, "stopped_count": 1}
    assert d["volumes"] == {"count": 2, "bytes": 850_000_000, "unused_count": 1, "unused_bytes": 50_000_000}
    assert d["build_cache_bytes"] == 10_000_000
    text = json.dumps(d)
    assert not any(n in text for n in ("argus-lab-api", "stopped-job", "pgdata", "orphan", "old:0", "sha256"))


def test_detailed_logs_take_a_bounded_window_and_a_stream(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(svc, "docker", _fake_docker(calls))
    d = svc.read_gateway(["containers", "argus-lab-api", "logs_window"], {"minutes": ["15"], "stream": ["stderr"]})
    assert d["minutes"] == 15 and d["stream"] == "stderr" and len(d["lines"]) == 5
    log_call = next(c for c in calls if "/logs" in c)
    assert "stdout=0" in log_call and "stderr=1" in log_call and "since=" in log_call and "tail=500" in log_call
    for bad in ({"minutes": ["0"]}, {"minutes": ["121"]}, {"stream": ["all"]}):
        with pytest.raises(svc.Err) as e:
            svc.read_gateway(["containers", "argus-lab-api", "logs_window"], bad)
        assert e.value.code == 400


def test_search_logs_uses_a_named_pattern_only(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "docker", _fake_docker([]))
    d = svc.read_gateway(["containers", "argus-lab-api", "search"], {"pattern": ["timeout"], "minutes": ["30"]})
    assert d["pattern"] == "timeout" and d["matched"] == 1 and "db timeout" in d["lines"][0]
    d = svc.read_gateway(["containers", "argus-lab-api", "search"], {"pattern": ["error"], "minutes": ["30"]})
    assert d["matched"] == 2                                              # ERROR + Traceback
    with pytest.raises(svc.Err) as e:
        svc.read_gateway(["containers", "argus-lab-api", "search"], {"pattern": ["hunter.*"]})
    assert e.value.code == 400                                            # never free text or a model's regex


def test_a_container_outside_the_allowlist_is_refused(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "docker", _fake_docker([]))
    for what in ("top", "logs_window", "search"):
        with pytest.raises(svc.Err) as e:
            svc.read_gateway(["containers", "argus-v18-agent", what], {"pattern": ["error"]})
        assert e.value.code in (403, 404)


@pytest.mark.parametrize("line", ["KeyError: 'FEATURE_FLAGS' in settings.load()", "ValueError: bad port",
                                  "java.lang.RuntimeException: boom", "3 errors in the last batch", "ERROR db down",
                                  "Traceback (most recent call last):", "FATAL: the database system is starting up"])
def test_the_error_pattern_finds_exception_class_names_and_plurals(tmp_path, monkeypatch, line):
    """EVAL-search-logs: `\\berror\\b` missed `KeyError: …` (no word boundary inside the class name), so a search told
    the model "0 errors" for a log that had one (`health-api-vm166-01`)."""
    assert _service(tmp_path, monkeypatch).LOG_PATTERNS["error"].search(line)


@pytest.mark.parametrize("line", ["GET /items 200", "service running", "no route configured", "mirror sync done"])
def test_the_error_pattern_does_not_match_ordinary_lines(tmp_path, monkeypatch, line):
    assert not _service(tmp_path, monkeypatch).LOG_PATTERNS["error"].search(line)


def test_the_gateway_and_the_catalogue_name_the_same_patterns(tmp_path, monkeypatch):
    from argus.capabilities.catalog import SEARCH_PATTERNS
    svc = _service(tmp_path, monkeypatch)
    assert set(svc.LOG_PATTERNS) == set(SEARCH_PATTERNS)


# --- the capabilities ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(NEW))
def test_the_four_are_level_2_safe_docker_read_capabilities_offered_to_no_class(name):
    s = SPECS[name]
    model, kinds = NEW[name]
    assert (s.model_name, s.level, s.safety_class, s.executor) == (model, 2, "READ_ONLY_SAFE", "docker_read")
    assert set(s.target_kinds) == kinds
    assert [c.name for c in CLASSES if s.tags & c.tool_tags] == []
    pol = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    assert pol["capabilities"][name]["max_per_incident"] >= 2


class Client:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def get(self, path, params=None):
        self.asked.append((path, params))
        return self.answer


def _call(name, target, client, **args):
    s = SPECS[name]
    return s.impl(s.args_model(**args), target, None, client)


def test_the_capabilities_ask_their_route_and_say_what_they_found():
    c = Client({"processes": [{"pid": 1, "ppid": 0, "command": "python"}], "count": 1, "collected_at": None})
    r = _call("container.processes", API, c)
    assert c.asked == [("/containers/argus-lab-api/top", None)] and "1 processes: python" in r.model_text
    c = Client({"images": {"count": 2, "bytes": 450_000_000, "unused_count": 1, "unused_bytes": 300_000_000},
                "containers": {"count": 2, "writable_bytes": 6_000_000, "stopped_count": 1},
                "volumes": {"count": 2, "bytes": 850_000_000, "unused_count": 1, "unused_bytes": 50_000_000},
                "build_cache_bytes": 10_000_000, "collected_at": None})
    r = _call("docker.disk_usage", HOST, c)
    assert c.asked == [("/docker/df", None)] and "images 2 (450000000 bytes, 1 unused" in r.model_text
    c = Client({"lines": ["a", "b"], "minutes": 15, "stream": "stderr", "truncated": False, "collected_at": None})
    r = _call("container.detailed_logs", API, c, minutes=15, stream="stderr")
    assert c.asked == [("/containers/argus-lab-api/logs_window", {"minutes": 15, "stream": "stderr"})]
    assert "2 stderr log lines in 15 min" in r.model_text
    c = Client({"pattern": "timeout", "matched": 3, "lines": ["x"], "minutes": 30, "truncated": False,
                "collected_at": None})
    r = _call("container.search_logs", API, c, pattern="timeout")
    assert c.asked == [("/containers/argus-lab-api/search", {"pattern": "timeout", "minutes": 30})]
    assert "3 lines matched 'timeout' in 30 min" in r.model_text


def test_the_model_cannot_pass_a_pattern_outside_the_set():
    with pytest.raises(Exception):
        SPECS["container.search_logs"].args_model(pattern="hunter2|password")
