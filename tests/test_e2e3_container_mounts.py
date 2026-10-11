"""E2E-3: `container.status` shows the declared host filesystems a container has mounted (the SC-05 writer link).

In SC-05 the model saw `/srv/argus-lab-fill` at 92.6 % and the filler running, but only the filler's logs said it
writes that filesystem; without them it named the host (E2E-2 step 2, `inc_de65a12688bc`). Docker already knows the
binds. The read-gateway matches each bind source to the host's declared mounts (its config, rendered from the
inventory) and returns only the declared mount and rw/ro: a source under no declared mount other than `/` is counted,
never named, so no other host path (the deploy home, its secrets) leaves the gateway.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from argus.capabilities.catalog import NoArgs, container_status
from argus.domain.model import TargetInfo, TargetRef

ROOT = Path(__file__).resolve().parents[1]
FILL = "/srv/argus-lab-fill"


def _service(tmp_path, monkeypatch, mounts=("/", FILL)):
    cfg = tmp_path / "target.json"
    cfg.write_bytes(json.dumps({"host": "vm-166", "containers": ["argus-lab-filler"], "mounts": list(mounts)}).encode())
    monkeypatch.setenv("ROLE", "exporter")
    monkeypatch.setenv("TA_CONFIG", str(cfg))
    spec = importlib.util.spec_from_file_location("ta_service_e2e3", ROOT / "services" / "target" / "service.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _inspect(svc, monkeypatch, mounts):
    raw = {"Id": "abc123def4567890", "State": {"Status": "running"}, "HostConfig": {}, "Config": {},
           "NetworkSettings": {"Networks": {}}, "Mounts": mounts}
    monkeypatch.setattr(svc, "djson", lambda path: raw)
    return svc.inspect("argus-lab-filler")


def test_gateway_names_a_declared_mount_with_rw_and_counts_the_rest(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch)
    d = _inspect(svc, monkeypatch, [
        {"Type": "bind", "Source": FILL, "Destination": "/fill", "RW": True},
        {"Type": "bind", "Source": "/opt/argus-v18/app/deploy/lab/workloads", "Destination": "/w", "RW": False},
        {"Type": "volume", "Name": "somevolume", "Source": "/var/lib/docker/volumes/x/_data", "RW": True}])
    assert d["host_mounts"] == [{"mount": FILL, "rw": True}]
    assert d["other_binds"] == 1                                     # the workloads bind: counted, not named
    assert "/opt/argus-v18" not in json.dumps(d) and "somevolume" not in json.dumps(d)


def test_gateway_matches_a_subdirectory_to_its_declared_mount_read_only(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch)
    d = _inspect(svc, monkeypatch, [{"Type": "bind", "Source": FILL + "/sub/dir", "Destination": "/x", "RW": False}])
    assert d["host_mounts"] == [{"mount": FILL, "rw": False}]
    assert d["other_binds"] == 0
    other = _inspect(svc, monkeypatch, [{"Type": "bind", "Source": FILL + "-other", "Destination": "/y", "RW": True}])
    assert other["host_mounts"] == [] and other["other_binds"] == 1  # a prefix of the name is not the same mount


def test_gateway_without_binds_reports_none(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch)
    d = _inspect(svc, monkeypatch, [])
    assert d["host_mounts"] == [] and d["other_binds"] == 0


class Client:
    def __init__(self, extra):
        self.extra = extra

    def get(self, path, params=None):
        return {"id": "abc123def456", "state": "running", "health": "none", "restart_count": 0, "networks": [],
                "collected_at": "2026-10-11T12:00:00+00:00", **self.extra}


FILLER = TargetRef.parse("vm-166/container:argus-lab-filler")


def test_status_tells_the_model_which_declared_filesystem_a_container_writes():
    r = container_status(NoArgs(), FILLER, TargetInfo(ref=FILLER),
                         Client({"host_mounts": [{"mount": FILL, "rw": True}], "other_binds": 1}))
    assert f"host_mounts={FILL}(rw)" in r.model_text and "other_binds=1" in r.model_text


def test_status_of_a_container_without_mounts_is_unchanged():
    before = container_status(NoArgs(), FILLER, TargetInfo(ref=FILLER), Client({})).model_text      # an older gateway
    after = container_status(NoArgs(), FILLER, TargetInfo(ref=FILLER),
                             Client({"host_mounts": [], "other_binds": 0})).model_text
    assert before == after and "host_mounts" not in after and "other_binds" not in after
