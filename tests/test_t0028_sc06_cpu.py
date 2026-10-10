"""T-0028 / SC-06: a container throttled at its CPU quota (class `cpu_saturation`, RB-006; phase 11).

RB-006 keeps two triggers apart: a busy host, and a container throttled at its quota even when the host is quiet.
This task is the second (SC-06: a CPU burner capped at `cpus: 0.3`): cAdvisor's CFS counters give the share of CPU
periods in which the container was throttled; 50 % or more for 5 minutes matches (an initial threshold, calibrated in
the lab). The read gateway reports the container's CPU limit, so a diagnosis can name the quota from evidence.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

from argus.adapters.outbound.llm import ScriptedLLM
from argus.domain.model import IncidentOutcome, MetricSnapshot, TargetRef, utcnow
from test_core import FakeMetrics, incident, make_app  # noqa: F401  (make_app = fixture)

ROOT = Path(__file__).resolve().parents[1]
BURNER = "vm-166/container:argus-lab-burner"


def _yaml(*parts):
    return yaml.safe_load(ROOT.joinpath(*parts).read_text(encoding="utf-8"))


def _service(tmp_path, monkeypatch):
    cfg = tmp_path / "target.json"
    cfg.write_bytes(b'{"host": "vm-166", "containers": ["argus-lab-burner"]}')
    monkeypatch.setenv("ROLE", "exporter")
    monkeypatch.setenv("TA_CONFIG", str(cfg))
    spec = importlib.util.spec_from_file_location("ta_service_t0028", ROOT / "services" / "target" / "service.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _snap(**values) -> MetricSnapshot:
    return MetricSnapshot(target=TargetRef.parse(BURNER), observed_at=utcnow(), values=values)


# --- the read gateway reports the CPU limit -------------------------------------------------------------------------
def test_inspect_reports_the_cpu_limit_from_nano_cpus_or_the_cfs_quota(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch)
    base = {"State": {"Status": "running"}, "Config": {}}
    for hc, want in (({"NanoCpus": 300_000_000}, 0.3), ({"CpuQuota": 50_000, "CpuPeriod": 100_000}, 0.5),
                     ({"CpuQuota": 20_000}, 0.2), ({}, None), ({"NanoCpus": 0, "CpuQuota": -1}, None)):
        monkeypatch.setattr(svc, "djson", lambda path, hc=hc: {**base, "HostConfig": hc})
        assert svc.inspect("argus-lab-burner")["cpu_limit_cores"] == want, hc


def test_container_status_tells_the_model_the_cpu_limit():
    from argus.capabilities import catalog
    src = (ROOT / "argus" / "capabilities" / "catalog.py").read_text(encoding="utf-8")
    assert "cpu_limit_cores=" in src and hasattr(catalog, "build_catalog")


# --- signal, detector, class ----------------------------------------------------------------------------------------
def test_the_signal_is_the_5_minute_minimum_of_the_throttled_share():
    sig = _yaml("config", "signals.yaml")["container_cpu_throttled_ratio_5m"]
    assert sig.startswith("min_over_time(") and "[5m:30s]" in sig
    assert 'container_cpu_cfs_throttled_periods_total{argus_host="$host",name="$name"}' in sig
    assert 'container_cpu_cfs_periods_total{argus_host="$host",name="$name"}' in sig and "> 0" in sig
    assert sig.count("[3m]") == 2 and "[1m]" not in sig     # cAdvisor's samples are 35-53 s apart: 1m is mostly empty


def test_the_detector_matches_a_container_throttled_while_using_its_quota():
    from argus.detectors.classes import cpu_saturation
    r = cpu_saturation(_snap(container_cpu_throttled_ratio_5m=0.97, container_cpu_quota_used_ratio_5m=0.99))
    assert r.matched and any("97% of its CPU periods" in f for f in r.findings)
    assert any("99% of its CPU quota" in f for f in r.findings)
    assert cpu_saturation(_snap(container_cpu_throttled_ratio_5m=0.5, container_cpu_quota_used_ratio_5m=0.8)).matched
    assert not cpu_saturation(_snap(container_cpu_throttled_ratio_5m=0.2, container_cpu_quota_used_ratio_5m=0.99)).matched


def test_a_bursty_container_far_below_its_quota_is_not_saturated():
    """Step 2 on vm-166: argus-lab-api (0.2 cores, health checks in bursts) had 61 % of its active periods throttled
    while using 4 % of its quota. The throttled share counts only the periods it ran in: alone it is not saturation."""
    from argus.detectors.classes import cpu_saturation
    r = cpu_saturation(_snap(container_cpu_throttled_ratio_5m=0.61, container_cpu_quota_used_ratio_5m=0.04))
    assert not r.matched


def test_the_detector_treats_a_missing_signal_as_unknown():
    from argus.detectors.classes import cpu_saturation
    for vals in ({"container_cpu_throttled_ratio_5m": None, "container_cpu_quota_used_ratio_5m": 0.99},
                 {"container_cpu_throttled_ratio_5m": 0.97, "container_cpu_quota_used_ratio_5m": None}):
        r = cpu_saturation(_snap(**vals))
        assert not r.matched and any("unknown" in f for f in r.findings), vals


def test_the_quota_used_signal_normalizes_usage_to_the_quota():
    sig = _yaml("config", "signals.yaml")["container_cpu_quota_used_ratio_5m"]
    assert sig.startswith("min_over_time(") and "[5m:30s]" in sig and "[3m]" in sig
    assert 'container_cpu_usage_seconds_total{argus_host="$host",name="$name"}' in sig
    assert 'container_spec_cpu_quota{argus_host="$host",name="$name"}' in sig
    assert 'container_spec_cpu_period{argus_host="$host",name="$name"}' in sig


def test_the_class_is_registered_for_containers_with_rb006():
    from argus.detectors.classes import classes_for
    spec = next(c for c in classes_for("container") if c.name == "cpu_saturation")
    assert spec.runbook_ids == ["RB-006"] and spec.strategy == "model_loop" and spec.family == "saturation"
    assert spec.required_signals == {"container_cpu_throttled_ratio_5m", "container_cpu_quota_used_ratio_5m"}
    assert "cpu_saturation" not in [c.name for c in classes_for("host")]      # the busy-host trigger is not this task


# --- the alert ------------------------------------------------------------------------------------------------------
def test_the_throttling_alert_names_the_container_and_only_argus_objects():
    rules = _yaml("deploy", "monitoring", "alerts.yml")["groups"][0]["rules"]
    a = next(r for r in rules if r.get("alert") == "ContainerCpuThrottled")
    assert a["for"] == "5m" and ">= 0.5" in a["expr"]
    assert "[1m]" not in a["expr"]                                     # step 2 on vm-166: a 1m rate never fired
    assert "container_spec_cpu_quota" in a["expr"] and ">= 0.8" in a["expr"]   # and it uses its quota (not bursts)
    assert 'label_replace(' in a["expr"] and '"container", "$1", "name", "(.*)"' in a["expr"]   # the intake's label
    assert 'name=~"argus-.*"' in a["expr"]                                    # never another deployment's container


# --- the lab workload -----------------------------------------------------------------------------------------------
def test_the_burner_is_a_bounded_lab_workload():
    svc = _yaml("deploy", "lab", "compose.lab.yml")["services"]["argus-lab-burner"]
    assert svc["container_name"] == "argus-lab-burner" and svc["profiles"] == ["sc06"]
    assert float(svc["cpus"]) == 0.3 and svc["network_mode"] == "none" and svc["restart"] == "no"
    assert svc["mem_limit"] and svc["pids_limit"] <= 16
    assert int(svc["environment"]["MAX_S"]) <= 1800                          # it stops by itself
    assert (ROOT / "deploy" / "lab" / "workloads" / "burn.py").exists()


def test_the_burner_stops_by_itself(monkeypatch):
    spec = importlib.util.spec_from_file_location("burn_t0028", ROOT / "deploy" / "lab" / "workloads" / "burn.py")
    burn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(burn)
    monkeypatch.setenv("MAX_S", "0.2")
    assert burn.main() == 0


def test_the_inventory_declares_the_burner():
    inv = _yaml("config", "inventory.yaml")
    assert BURNER in [t["ref"] for t in inv["targets"]]


# --- an investigation -----------------------------------------------------------------------------------------------
def test_a_scripted_diagnosis_reads_the_limit_and_names_the_burner(make_app, monkeypatch):
    from test_core import FakeTargetAgent
    gw = FakeTargetAgent.data["http://argus-v18-tunnel:18701"]                # vm-166's read gateway
    monkeypatch.setitem(gw, "/containers/argus-lab-burner/status",
                        {"id": "ddd444", "state": "running", "health": "none", "restart_count": 0, "oom_killed": False,
                         "exit_code": 0, "memory_limit_bytes": 33554432, "cpu_limit_cores": 0.3})
    monkeypatch.setitem(gw, "/containers/argus-lab-burner/stats",
                        {"memory_usage_bytes": 9000000, "memory_limit_bytes": 33554432, "cpu_percent": 29.8})
    def script(ctx: str):
        if "cpu_limit_cores" not in ctx:
            return {"calls": [("get_container_status", {"target": BURNER}),
                              ("get_container_resources", {"target": BURNER})]}
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        return {"calls": [("conclude", {"diagnosis": "argus-lab-burner is CPU-bound at its 0.3-core quota (RB-006 H2)",
                                        "evidence_ids": ids[-2:], "confidence": "medium",
                                        "root_cause_target": BURNER})]}
    metrics = FakeMetrics({BURNER: {"container_cpu_throttled_ratio_5m": 0.95, "container_cpu_quota_used_ratio_5m": 0.99,
                                    "restarts_10m": 0}})
    app = make_app(llm=ScriptedLLM(script), metrics=metrics)
    inc = app.runner.run(incident(app, BURNER, reason="ContainerCpuThrottled").id)
    assert inc.incident_class == "cpu_saturation" and inc.outcome == IncidentOutcome.diagnosed
    assert "container.status" in [e.capability for e in app.store.list_evidence(inc.id)]
    assert json.dumps(inc.model_dump(mode="json"))                            # serializable as stored
