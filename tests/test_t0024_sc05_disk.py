"""T-0024 / SC-05: host disk almost full (class `disk_pressure`, RB-005).

node-exporter (T-0022) publishes every filesystem; the signals read only the host target's declared mounts
(`$mounts`, from the inventory), so a data disk is covered like `/`. The class matches at 90 % for 5 minutes. The lab
fills a dedicated 256 MiB loop filesystem, never the root disk.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

from argus.adapters.outbound.llm import ScriptedLLM
from argus.domain.model import IncidentOutcome, MetricSnapshot, TargetRef, utcnow

from test_core import FakeMetrics, incident, make_app  # noqa: F401  (make_app is a fixture)

ROOT = Path(__file__).resolve().parents[1]
HOST = "vm-166/host:vm-166"
FILLER = "vm-166/container:argus-lab-filler"
FILL = "/srv/argus-lab-fill"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _yaml(*parts):
    return yaml.safe_load(ROOT.joinpath(*parts).read_text(encoding="utf-8"))


# --- signals: per declared mount ---------------------------------------------------------------------
def test_disk_signals_read_only_the_declared_mounts_of_the_host():
    sig = _yaml("config", "signals.yaml")
    for name in ("host_disk_used_ratio_5m", "host_disk_hours_to_full"):
        assert 'argus_host="$host"' in sig[name] and 'mountpoint=~"$mounts"' in sig[name], name
    assert sig["host_disk_used_ratio_5m"].startswith("max(min_over_time(") and "[5m:30s]" in sig["host_disk_used_ratio_5m"]
    assert "deriv(" in sig["host_disk_hours_to_full"] and "[15m]" in sig["host_disk_hours_to_full"]


def test_snapshot_fills_mounts_from_the_inventory(monkeypatch):
    import argus.adapters.outbound.config_adapters as ca
    queries = []

    class Resp:
        def __init__(self, v):
            self.v = v

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"result": [{"value": [1.9e9, self.v]}]}}

    def fake_get(url, params, timeout):
        queries.append(params["query"])
        return Resp("1")
    monkeypatch.setattr(ca.httpx, "get", fake_get)
    monkeypatch.setattr(ca.time, "time", lambda: 1.9e9)
    inv = ca.YamlInventory((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    m = ca.PrometheusMetrics(inv, _yaml("config", "signals.yaml"))
    m.snapshot(TargetRef.parse(HOST), {"host_disk_used_ratio_5m"})
    q = queries[-1]
    assert f'mountpoint=~"/|{FILL}"' in q and 'argus_host="vm-166"' in q and "$" not in q


def test_inventory_refuses_a_mount_path_with_regex_characters():
    import argus.adapters.outbound.config_adapters as ca
    text = (ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8")
    bad = text.replace(f'mounts: ["/", "{FILL}"]', 'mounts: ["/", "/srv/.*"]')
    assert bad != text
    with pytest.raises(ValueError, match="mount"):
        ca.YamlInventory(bad)


# --- the detector and the class ----------------------------------------------------------------------
def _snap(**values):
    return MetricSnapshot(target=TargetRef.parse(HOST), observed_at=utcnow(), values=values)


def test_detector_matches_at_ninety_percent_and_gives_the_time_to_full():
    from argus.detectors.classes import disk_pressure as det
    r = det(_snap(host_disk_used_ratio_5m=0.92, host_disk_hours_to_full=0.25))
    assert r.matched and any("92%" in f for f in r.findings) and any("15 min" in f for f in r.findings)
    r = det(_snap(host_disk_used_ratio_5m=0.95, host_disk_hours_to_full=None))
    assert r.matched and any("not growing" in f for f in r.findings)
    assert not det(_snap(host_disk_used_ratio_5m=0.5, host_disk_hours_to_full=None)).matched


def test_detector_treats_a_missing_ratio_as_unknown():
    from argus.detectors.classes import disk_pressure as det
    r = det(_snap(host_disk_used_ratio_5m=None, host_disk_hours_to_full=None))
    assert not r.matched and any("unknown" in f for f in r.findings)


def test_the_class_is_registered_for_hosts_with_rb005():
    from argus.detectors.classes import CLASSES, classes_for
    c = next(c for c in CLASSES if c.name == "disk_pressure")
    assert (c.family, c.runbook_ids, c.branch_runbook_ids, c.strategy) == ("saturation", ["RB-005"], ["RB-019"],
                                                                          "confirm_then_reason")   # E2E-5
    assert c.target_kinds == {"host"} and c.required_signals == {"host_disk_used_ratio_5m", "host_disk_hours_to_full"}
    assert {"host", "disk", "logs", "container", "knowledge"} <= c.tool_tags
    assert c in classes_for("host") and c not in classes_for("container")


def test_scripted_diagnosis_reads_the_disk_and_names_the_filler(make_app):
    def script(ctx: str):
        if "inodes_used" not in ctx:                                   # host.disk_usage not read yet
            return {"calls": [("get_disk_usage", {"target": HOST, "mount": FILL})]}
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        return {"calls": [("conclude", {"diagnosis": "argus-lab-filler keeps writing to /srv/argus-lab-fill (RB-005 H7)",
                                        "evidence_ids": ids[-1:], "confidence": "medium",
                                        "root_cause_target": FILLER})]}
    metrics = FakeMetrics({HOST: {"host_disk_used_ratio_5m": 0.92, "host_disk_hours_to_full": 0.3}})
    app = make_app(llm=ScriptedLLM(script), metrics=metrics)
    inc = app.runner.run(incident(app, HOST, reason="the lab filesystem is filling up").id)
    assert inc.incident_class == "disk_pressure" and inc.outcome == IncidentOutcome.diagnosed
    assert "host.disk_usage" in [e.capability for e in app.store.list_evidence(inc.id)]


def test_rb005_names_its_detector_and_is_bumped():
    text = (ROOT / "argus" / "runbooks" / "RB-005-host-disk-almost-full.md").read_text(encoding="utf-8")
    meta = yaml.safe_load(re.search(r"```yaml\n(.*?)```", text, re.S).group(1))
    assert meta["detector"] == "disk_pressure"
    assert meta["version"] == "1.0.3" and str(meta["last_reviewed"]) == "2026-10-09"   # + OP-001 (1.0.1) merged
    assert str(meta["last_tested"]) == "2026-10-09"                    # SC-05 DIAGNOSED on vm-166
    assert "No disk detector was found" not in text


# --- monitoring --------------------------------------------------------------------------------------
def test_host_disk_alert_covers_every_real_filesystem():
    rules = _yaml("deploy", "monitoring", "alerts.yml")
    a = next(r for g in rules["groups"] for r in g["rules"] if r.get("alert") == "HostDiskPressure")
    assert 'fstype=~"ext4|xfs|btrfs"' in a["expr"] and 'mountpoint="/"' not in a["expr"]
    assert "by (argus_host)" in a["expr"] and a["for"] == "5m"


def test_host_views_see_mounts_created_after_the_container_started():
    mon = _yaml("deploy", "monitoring", "compose.monitoring.yml")["services"]
    assert "/:/host:ro,rslave" in mon["argus-v18-node-exporter"]["volumes"]
    tgt = _yaml("deploy", "target", "compose.target.yml")["services"]
    assert "/:/rootfs:ro,rslave" in tgt["argus-v18-host-probe"]["volumes"]


def test_host_probe_refuses_a_declared_mount_that_is_not_mounted(tmp_path, monkeypatch):
    cfg = tmp_path / "target.json"
    cfg.write_bytes(json.dumps({"host": "vm-166", "containers": [], "mounts": ["/", FILL]}).encode())
    (tmp_path / "rootfs" / "srv" / "argus-lab-fill").mkdir(parents=True)          # a plain directory, no mount
    (tmp_path / "host_probe_token").write_bytes(b"t0ken")
    monkeypatch.setenv("ROLE", "host_probe")
    monkeypatch.setenv("TA_CONFIG", str(cfg))
    monkeypatch.setenv("TA_SECRETS", str(tmp_path))
    monkeypatch.setenv("TA_ROOTFS", str(tmp_path / "rootfs"))
    svc = _load("ta_service_t0024", ROOT / "services" / "target" / "service.py")
    with pytest.raises(svc.Err) as e:
        svc.host_probe(["disk"], {"mount": [FILL]})
    assert e.value.code == 409 and "not mounted" in str(e.value.args)
    if hasattr(__import__("os"), "statvfs"):                                    # Linux (CI, the VMs)
        assert svc.host_probe(["disk"], {"mount": ["/"]})["mount"] == "/"        # the root view itself is fine


# --- the lab -----------------------------------------------------------------------------------------
def test_sc05_filler_is_a_bounded_lab_workload_without_network():
    s = _yaml("deploy", "lab", "compose.lab.yml")["services"]["argus-lab-filler"]
    assert s["profiles"] == ["sc05"] and s["network_mode"] == "none" and s["restart"] == "no"
    assert s["mem_limit"] and s["cpus"] and s["pids_limit"] and "ports" not in s
    assert f"{FILL}:/fill" in s["volumes"]
    env = s["environment"]
    assert int(env["TARGET_PCT"]) == 92 and int(env["MAX_FS_MIB"]) <= 512


def test_filler_refuses_a_filesystem_larger_than_its_bound(monkeypatch):
    fill = _load("lab_fill", ROOT / "deploy" / "lab" / "workloads" / "fill.py")

    class St:
        def __init__(self, mib):
            self.f_frsize, self.f_blocks, self.f_bavail = 1 << 20, mib, mib
    monkeypatch.setattr(fill.os, "statvfs", lambda p: St(50_000), raising=False)   # the root disk: 49 GiB
    with pytest.raises(SystemExit, match="refusing"):
        fill.check_fs("/fill", max_mib=512)
    monkeypatch.setattr(fill.os, "statvfs", lambda p: St(240), raising=False)      # the lab filesystem
    assert fill.check_fs("/fill", max_mib=512) == 240


def test_inventory_declares_the_filler():
    inv = _yaml("config", "inventory.yaml")
    f = next(t for t in inv["targets"] if t["ref"] == FILLER)
    assert f["depends_on"] == [HOST]                  # a dependent of the host: in its incident scope (ARCHITECTURE §5)
    cfg = json.loads((ROOT / "deploy" / "target" / "config" / "vm-166.json").read_text(encoding="utf-8"))
    assert "argus-lab-filler" in cfg["containers"] and FILL in cfg["mounts"]


def test_lab_fill_mount_script_is_idempotent_and_bounded():
    s = (ROOT / "ops" / "lab-fill-mount.sh").read_text(encoding="utf-8")
    assert "\r\n" not in s and "set -eu" in s
    for part in ("mountpoint -q", "mkfs.ext4", "-m 0", "256M", "/opt/argus-v18/lab/", FILL, "--remove",
                 "nodev,nosuid,noexec"):
        assert part in s, part
    assert "fstab" not in s                                                    # never persisted in host config
