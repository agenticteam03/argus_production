"""OP-005: early restarts count, while scrape gaps stay unknown."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def _exporter(tmp_path, monkeypatch):
    cfg = tmp_path / "target.json"
    cfg.write_bytes(b'{"host":"vm-166","containers":["argus-lab-worker"]}')
    monkeypatch.setenv("ROLE", "exporter")
    monkeypatch.setenv("TA_CONFIG", str(cfg))
    spec = importlib.util.spec_from_file_location("target_op005", ROOT / "services/target/service.py")
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    return service


def test_creation_time_comes_from_docker_inspect(tmp_path, monkeypatch):
    service = _exporter(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "djson", lambda path: {
        "Id": "abc123def456", "Created": "2026-10-09T07:57:00.123456789Z", "RestartCount": 3,
        "State": {"Status": "running", "Running": True}, "HostConfig": {}, "Config": {},
    })
    assert service.inspect("argus-lab-worker")["created_at_seconds"] == pytest.approx(1791532620.1234567)


def test_exporter_publishes_creation_time_only_for_existing_containers(tmp_path, monkeypatch):
    service = _exporter(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "inspect", lambda name: {
        "restart_count": 3, "created_at_seconds": 1791532620.1234567, "running": False,
        "exit_code": 1, "oom_killed": False, "health": "none",
    })
    monkeypatch.setattr(service.time, "sleep", lambda seconds: (_ for _ in ()).throw(StopIteration))
    with pytest.raises(StopIteration):
        service.collect()
    created_line = next(line for line in service._metrics.splitlines() if line.startswith("argus_container_created_seconds{"))
    assert created_line.startswith('argus_container_created_seconds{container="argus-lab-worker"} ')
    assert float(created_line.split()[-1]) == pytest.approx(1791532620.1234567)

    monkeypatch.setattr(service, "inspect", lambda name: (_ for _ in ()).throw(service.Err(404, "absent")))
    with pytest.raises(StopIteration):
        service.collect()
    assert "argus_container_created_seconds" not in service._metrics


def test_signal_uses_the_approved_promql_and_promtool_checks_the_same_expression():
    signals = yaml.safe_load((ROOT / "config/signals.yaml").read_text(encoding="utf-8"))
    count = 'argus_container_restart_count{argus_host="$host",container="$name"}'
    created = 'argus_container_created_seconds{argus_host="$host",container="$name"}'
    expected = (f'clamp_min(({count} and on(argus_host,container) (time() - {created} < 600)) '
                f'or on(argus_host,container) ({count} - {count} offset 10m), 0)')
    assert signals["restarts_10m"] == expected
    rules = yaml.safe_load((ROOT / "tests/promql/op005_rules.yml").read_text(encoding="utf-8"))
    assert rules["groups"][0]["rules"][0]["expr"] == expected.replace("$host", "vm-166").replace("$name", "argus-lab-worker")


def test_the_restart_loop_alert_counts_like_the_signal():
    """Review of PR #41: the alert must count restarts like `restarts_10m` (young-first, a gap is unknown). With pulled
    alerts (T-0022, ACR-0003 proposed) the alert opens the incident; an old `max - min` alert would see a young loop later than the
    detector, or not at all."""
    signals = yaml.safe_load((ROOT / "config/signals.yaml").read_text(encoding="utf-8"))
    every_container = signals["restarts_10m"].replace('{argus_host="$host",container="$name"}', "")
    rules = yaml.safe_load((ROOT / "deploy/monitoring/alerts.yml").read_text(encoding="utf-8"))
    alert = next(r for g in rules["groups"] for r in g["rules"] if r.get("alert") == "ContainerRestartLoop")
    assert alert["expr"] == f"{every_container} >= 3"
