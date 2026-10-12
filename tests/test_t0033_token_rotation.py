"""T-0033 (Phase 13): an executor token is rotated while Argus runs.

A target service reads its token at start (services/target/service.py), so a rotation restarts it with the new token.
The agent's tools process also read its copy only at start, so after a rotation every read of that executor was
refused (HTTP 401, `forbidden`) until the worker restarted. The dispatcher now re-reads the token file once when an
executor rejects the token, and retries once if the file changed: the new token is used without a restart. A token
that is still rejected stays a `forbidden` error (one retry at most, never a loop), and it is never the target's fault.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from argus.capabilities.catalog import NoArgs, build_catalog
from argus.capabilities.redaction import Redactor
from argus.capabilities.spec import ExecutorError
from argus.domain.model import TargetRef
from argus.infrastructure.wiring import Settings, tools_dispatcher
from argus.tooling.dispatch import Dispatcher
from argus.tooling.executors import ExecutorRegistry

ROOT = Path(__file__).resolve().parents[1]
TARGET = TargetRef.parse("vm-166/host:vm-166")
UPTIME = next(s for s in build_catalog() if s.name == "host.uptime")


class Probe:
    """A host probe that accepts one token, like the real service after a restart with a new token file."""
    valid = "new-token"
    calls: list[str] = []

    def __init__(self, url, token):
        self.token = token

    def get(self, path, params=None):
        Probe.calls.append(self.token)
        if self.token != Probe.valid:
            raise ExecutorError("forbidden", f"{path}: HTTP 401 bad token")
        return {"host": "vm-166", "uptime_seconds": 1234, "collected_at": "2026-10-12T16:00:00+00:00"}


class Inventory:
    def host(self, name):
        return type("H", (), {"executors": {"host_probe": "http://probe"}})()

    def target(self, ref):
        return None


def _dispatcher(stored: dict, reload=None) -> Dispatcher:
    Probe.calls = []
    reg = ExecutorRegistry()
    reg.register("host_probe", Probe)
    return Dispatcher(Inventory(), reg, dict(stored), Redactor(), reload=reload)


def test_a_rotated_token_is_read_again_and_the_read_succeeds():
    files = {("vm-166", "host_probe"): "new-token"}                     # the agent's copy was already replaced
    d = _dispatcher({("vm-166", "host_probe"): "old-token"}, reload=lambda h, ex: files.get((h, ex)))
    obs = d.call(UPTIME, NoArgs(), TARGET)
    assert obs.status == "ok" and Probe.calls == ["old-token", "new-token"]
    obs = d.call(UPTIME, NoArgs(), TARGET)                              # the new token is kept: no second reload
    assert obs.status == "ok" and Probe.calls[-1] == "new-token" and len(Probe.calls) == 3


def test_a_token_still_rejected_is_retried_once_at_most():
    d = _dispatcher({("vm-166", "host_probe"): "old-token"}, reload=lambda h, ex: "old-token")   # file not replaced yet
    obs = d.call(UPTIME, NoArgs(), TARGET)
    assert obs.status == "error" and obs.error_category == "forbidden" and Probe.calls == ["old-token"]
    files = {"tok": "other-wrong-token"}
    d = _dispatcher({("vm-166", "host_probe"): "old-token"}, reload=lambda h, ex: files["tok"])
    obs = d.call(UPTIME, NoArgs(), TARGET)
    assert obs.error_category == "forbidden" and Probe.calls == ["old-token", "other-wrong-token"]


def test_without_a_reload_the_dispatcher_behaves_as_before():
    d = _dispatcher({("vm-166", "host_probe"): "old-token"})
    obs = d.call(UPTIME, NoArgs(), TARGET)
    assert obs.error_category == "forbidden" and Probe.calls == ["old-token"]
    assert "vm-166" in obs.model_text and "forbidden" in obs.model_text


def test_the_tools_process_re_reads_its_token_files(tmp_path, monkeypatch):
    """tools_dispatcher (the MCP child, §12.6) wires the reload to the same secret files it read at start."""
    s = Settings(config_dir=ROOT / "config", secrets_dir=tmp_path)
    import yaml
    inv = yaml.safe_load((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    for host, h in inv["hosts"].items():
        for ex in h["executors"]:
            if ex != "prometheus":
                (tmp_path / host).mkdir(exist_ok=True)
                (tmp_path / host / f"{ex}_token").write_text("old-token", encoding="utf-8")
    _, d, _ = tools_dispatcher(s)
    assert d.credentials[("vm-166", "host_probe")] == "old-token"
    (tmp_path / "vm-166" / "host_probe_token").write_text("new-token\n", encoding="utf-8")
    assert d.reload("vm-166", "host_probe") == "new-token"
