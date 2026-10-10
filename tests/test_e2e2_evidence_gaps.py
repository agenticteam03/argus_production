"""E2E-2: the two evidence gaps the runner's batches found on vm-166 (E2E-1 step 3).

SC-05: the detector fires on a declared mount (the lab filesystem) but `host.disk_usage` read `/` by default, so the
model saw 93 % in the metric and 28 % in every read and escalated. Without a mount it now reads every declared mount.
SC-07: the backend's assigned network was only a comment, so the model guessed which container was misplaced. The
inventory now declares a container's networks and `container.status` says when it is not on them.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from argus.capabilities.catalog import DiskArgs, NoArgs, container_status, host_disk
from argus.capabilities.spec import ExecutorError
from argus.domain.model import TargetInfo, TargetRef

ROOT = Path(__file__).resolve().parents[1]
HOST = TargetRef.parse("vm-166/host:vm-166")
FILL = "/srv/argus-lab-fill"


class DiskClient:
    """The host-probe's /disk answer per mount; records what was asked."""

    def __init__(self):
        self.asked = []

    def get(self, path, params=None):
        self.asked.append((path, params))
        used = {"/": 28.0, FILL: 92.6}[params["mount"]]
        return {"mount": params["mount"], "used_percent": used, "free_mib": 100, "inodes_used_percent": 2.8,
                "collected_at": "2026-10-10T15:20:00+00:00"}


def test_disk_usage_without_a_mount_reads_every_declared_mount():
    client = DiskClient()
    r = host_disk(DiskArgs(), HOST, TargetInfo(ref=HOST, mounts=["/", FILL]), client)
    assert [p["mount"] for _, p in client.asked] == ["/", FILL]
    assert "vm-166:/ used=28.0%" in r.model_text and f"vm-166:{FILL} used=92.6%" in r.model_text
    assert [m["mount"] for m in r.values["mounts"]] == ["/", FILL]


def test_disk_usage_with_a_mount_reads_only_that_one_and_refuses_an_undeclared_one():
    client = DiskClient()
    r = host_disk(DiskArgs(mount=FILL), HOST, TargetInfo(ref=HOST, mounts=["/", FILL]), client)
    assert client.asked == [("/disk", {"mount": FILL})] and "92.6%" in r.model_text and "28.0%" not in r.model_text
    with pytest.raises(ExecutorError, match="not allowlisted"):
        host_disk(DiskArgs(mount="/etc"), HOST, TargetInfo(ref=HOST, mounts=["/", FILL]), DiskClient())


def test_disk_usage_without_a_mount_on_a_host_with_none_declared_is_refused():
    with pytest.raises(ExecutorError, match="no declared mount"):
        host_disk(DiskArgs(), HOST, TargetInfo(ref=HOST), DiskClient())


def test_the_model_is_told_that_no_mount_means_every_declared_mount():
    schema = DiskArgs.model_json_schema()["properties"]["mount"]
    assert DiskArgs().mount is None and "every declared mount" in schema["description"]


# --- SC-07: declared networks --------------------------------------------------------------------------------------
class StatusClient:
    def __init__(self, networks):
        self.networks = networks

    def get(self, path, params=None):
        return {"id": "abc123def456", "state": "running", "health": "healthy", "restart_count": 0,
                "networks": self.networks, "collected_at": "2026-10-10T15:20:00+00:00"}


BACKEND = TargetRef.parse("vm-166/container:argus-lab-backend")
CLIENT = TargetRef.parse("vm-166/container:argus-lab-client")


def test_status_says_when_a_container_is_not_on_its_declared_network():
    r = container_status(NoArgs(), BACKEND, TargetInfo(ref=BACKEND, networks=["argus-lab-app"]),
                         StatusClient(["argus-lab-iso"]))
    assert "networks=argus-lab-iso" in r.model_text and "declared_networks=argus-lab-app" in r.model_text
    assert "NOT on its declared network(s): argus-lab-app" in r.model_text


def test_status_of_a_container_on_its_declared_network_raises_nothing():
    r = container_status(NoArgs(), CLIENT, TargetInfo(ref=CLIENT, networks=["argus-lab-app"]),
                         StatusClient(["argus-lab-app", "argus-v18-mon"]))      # an extra network is not a problem
    assert "declared_networks=argus-lab-app" in r.model_text and "NOT on" not in r.model_text


def test_status_without_declared_networks_is_unchanged():
    r = container_status(NoArgs(), CLIENT, TargetInfo(ref=CLIENT), StatusClient(["argus-lab-app"]))
    assert "declared_networks" not in r.model_text and "NOT on" not in r.model_text


def test_the_inventory_declares_the_sc07_networks():
    from argus.adapters.outbound.config_adapters import YamlInventory
    inv = YamlInventory((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    assert inv.target(CLIENT).networks == ["argus-lab-app"]
    assert inv.target(BACKEND).networks == ["argus-lab-app"]               # its assigned network, not argus-lab-iso
