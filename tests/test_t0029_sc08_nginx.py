"""T-0029 / SC-08: nginx in front of a slow upstream (class `nginx_upstream_failure`, RB-015; phase 11).

A synthetic HTTP probe (the exporter, every declared `http_endpoints` of an active container) publishes the status
code; 502 and 504 are the proxy's own answers when its upstream fails or is too slow ("gateway errors"). An app's
503 is not one (the SC-03 api answers 503 when its cache is down: that is `dependency_unavailable`). Half or more of
the probes answered 502/504 over 5 minutes matches; the root cause is expected in the proxy's upstream.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import yaml

from argus.adapters.outbound.llm import ScriptedLLM
from argus.domain.model import IncidentOutcome, MetricSnapshot, TargetRef, utcnow
from test_core import FakeMetrics, incident, make_app  # noqa: F401  (make_app = fixture)

ROOT = Path(__file__).resolve().parents[1]
NGINX = "vm-166/container:argus-lab-nginx"
SLOW = "vm-166/container:argus-lab-slow"
URL = "http://argus-lab-nginx:8080/"


def _yaml(*parts):
    return yaml.safe_load(ROOT.joinpath(*parts).read_text(encoding="utf-8"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _service(tmp_path, monkeypatch):
    cfg = tmp_path / "target.json"
    cfg.write_bytes(b'{"host": "vm-166", "containers": ["argus-lab-nginx"], "http_endpoints": ["' + URL.encode()
                    + b'"], "http_probes": [{"owner": "argus-lab-nginx", "url": "' + URL.encode() + b'"}]}')
    monkeypatch.setenv("ROLE", "exporter")
    monkeypatch.setenv("TA_CONFIG", str(cfg))
    return _load("ta_service_t0029", ROOT / "services" / "target" / "service.py")


def _snap(**values) -> MetricSnapshot:
    return MetricSnapshot(target=TargetRef.parse(NGINX), observed_at=utcnow(), values=values)


# --- inventory, rendered config -------------------------------------------------------------------------------------
def test_the_inventory_declares_the_proxy_and_its_upstream():
    targets = {t["ref"]: t for t in _yaml("config", "inventory.yaml")["targets"]}
    assert targets[NGINX]["http_endpoints"] == [URL] and targets[NGINX]["depends_on"] == [SLOW]
    assert targets[SLOW]["tcp_ports"] == [8080]


def test_the_rendered_config_lists_an_http_probe_per_declared_endpoint():
    render = _load("render_t0029", ROOT / "ops" / "render_target_config.py")
    inv = _yaml("config", "inventory.yaml")
    cfg = render.render_host(inv, "vm-166")
    assert {"owner": "argus-lab-nginx", "url": URL} in cfg["http_probes"]
    assert {"owner": "argus-lab-api", "url": "http://argus-lab-api:8080/health"} in cfg["http_probes"]
    assert render.render_host(inv, "vm-095")["http_probes"] == []
    import json
    committed = json.loads((ROOT / "deploy" / "target" / "config" / "vm-166.json").read_text(encoding="utf-8"))
    assert committed == cfg                                                   # the committed file is up to date


# --- the exporter's probe -------------------------------------------------------------------------------------------
def test_the_exporter_publishes_the_status_and_a_gateway_error_flag(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch)
    probes = [{"owner": "argus-lab-nginx", "url": URL}]
    for status, gateway in ((504, 1), (502, 1), (503, 0), (500, 0), (200, 0), (None, 0)):
        monkeypatch.setattr(svc, "http_check", lambda url, s=status: {"status": s, "error": None, "duration_ms": 2001.0})
        lines = svc.http_probe_lines(probes, {"argus-lab-nginx"})
        lab = f'owner="argus-lab-nginx",url="{URL}"'
        assert f"argus_http_probe_gateway_error{{{lab}}} {gateway}" in lines, status
        assert f"argus_http_probe_status{{{lab}}} {status or 0}" in lines, status
        assert f"argus_http_probe_duration_seconds{{{lab}}} 2.0010" in lines


def test_the_exporter_probes_only_active_owners(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "http_check", lambda url: {"status": 504, "error": None, "duration_ms": 1.0})
    assert svc.http_probe_lines([{"owner": "argus-lab-nginx", "url": URL}], set()) == []   # SC-08 not running


# --- signal, detector, class ----------------------------------------------------------------------------------------
def test_the_signal_is_the_worst_endpoints_5_minute_gateway_error_share():
    sig = _yaml("config", "signals.yaml")["http_gateway_error_ratio_5m"]
    assert sig == 'max(avg_over_time(argus_http_probe_gateway_error{argus_host="$host",owner="$name"}[5m]))'


def test_the_detector_matches_at_half_the_probes_failing_at_the_gateway():
    from argus.detectors.classes import nginx_upstream_failure
    r = nginx_upstream_failure(_snap(http_gateway_error_ratio_5m=1.0))
    assert r.matched and any("100% of the probes" in f and "502/504" in f for f in r.findings)
    assert nginx_upstream_failure(_snap(http_gateway_error_ratio_5m=0.5)).matched
    assert not nginx_upstream_failure(_snap(http_gateway_error_ratio_5m=0.2)).matched


def test_the_detector_treats_a_missing_share_as_unknown():
    from argus.detectors.classes import nginx_upstream_failure
    r = nginx_upstream_failure(_snap(http_gateway_error_ratio_5m=None))
    assert not r.matched and any("unknown" in f for f in r.findings)


def test_the_class_is_registered_with_rb015_and_its_branches():
    from argus.detectors.classes import classes_for
    spec = next(c for c in classes_for("container") if c.name == "nginx_upstream_failure")
    assert spec.runbook_ids == ["RB-015"] and spec.branch_runbook_ids == ["RB-002", "RB-003"]
    assert spec.strategy == "plan_then_reason" and spec.family == "availability"
    assert spec.required_signals == {"http_gateway_error_ratio_5m"}


# --- the alert ------------------------------------------------------------------------------------------------------
def test_the_gateway_error_alert_names_the_proxy():
    rules = _yaml("deploy", "monitoring", "alerts.yml")["groups"][0]["rules"]
    a = next(r for r in rules if r.get("alert") == "HttpGatewayErrors")
    assert a["expr"] == "max by (argus_host, owner) (avg_over_time(argus_http_probe_gateway_error[5m])) >= 0.5"
    assert a["for"] == "2m"                                    # `owner` is the label the intake maps to the target


# --- the lab --------------------------------------------------------------------------------------------------------
def test_the_lab_proxy_times_out_before_its_slow_upstream_answers():
    svc = _yaml("deploy", "lab", "compose.lab.yml")["services"]
    ng, slow = svc["argus-lab-nginx"], svc["argus-lab-slow"]
    assert ng["profiles"] == slow["profiles"] == ["sc08"]
    assert re.fullmatch(r"nginx:\d+\.\d+(\.\d+)?-alpine", ng["image"])          # a pinned version, not latest
    for s in (ng, slow):
        assert "argus-lab-app" in s["networks"] and s["restart"] == "no" and s["mem_limit"] and s["pids_limit"] <= 32
    conf = (ROOT / "deploy" / "lab" / "nginx" / "default.conf").read_text(encoding="utf-8")
    timeout = int(re.search(r"proxy_read_timeout\s+(\d+)s;", conf).group(1))
    assert "proxy_pass http://argus-lab-slow:8080" in conf
    assert int(slow["environment"]["DELAY_S"]) > timeout                     # the upstream is slower: 504


def test_the_slow_upstream_waits_then_answers(monkeypatch):
    slow = _load("slow_t0029", ROOT / "deploy" / "lab" / "workloads" / "slow.py")
    assert slow.delay_s({"DELAY_S": "6"}) == 6.0 and slow.delay_s({}) == 5.0


# --- an investigation -----------------------------------------------------------------------------------------------
def test_a_scripted_diagnosis_reads_the_proxy_and_names_the_slow_upstream(make_app, monkeypatch):
    from test_core import FakeTargetAgent
    gw = FakeTargetAgent.data["http://argus-v18-tunnel:18701"]
    for name in ("argus-lab-nginx", "argus-lab-slow"):
        monkeypatch.setitem(gw, f"/containers/{name}/status",
                            {"id": "f0f0f0", "state": "running", "health": "none", "restart_count": 0,
                             "oom_killed": False, "exit_code": 0, "networks": ["argus-lab-app"]})
        monkeypatch.setitem(gw, f"/containers/{name}/logs", {"lines": [
            "upstream timed out (110: Connection timed out) while reading response header from upstream"
            if name == "argus-lab-nginx" else "slow: answering after 5 s"]})

    def script(ctx: str):
        if "argus-lab-slow: state=" not in ctx:
            return {"calls": [("get_container_status", {"target": SLOW}),
                              ("get_container_logs", {"target": NGINX, "tail": 20})]}
        ids = [line.split('"')[1] for line in ctx.splitlines() if line.startswith("<evidence id=")]
        return {"calls": [("conclude", {"diagnosis": "nginx returns 504: its upstream argus-lab-slow answers after its "
                                                     "2 s proxy_read_timeout (RB-015 H3)",
                                        "evidence_ids": ids[-2:], "confidence": "medium", "root_cause_target": SLOW})]}
    metrics = FakeMetrics({NGINX: {"http_gateway_error_ratio_5m": 1.0, "restarts_10m": 0, "health_unhealthy": None,
                                   "dependency_probe_min": 1}})
    app = make_app(llm=ScriptedLLM(script), metrics=metrics)
    inc = app.runner.run(incident(app, NGINX, reason="HttpGatewayErrors").id)
    assert inc.incident_class == "nginx_upstream_failure" and inc.outcome == IncidentOutcome.diagnosed
    assert inc.root_cause_target is not None and str(inc.root_cause_target) == SLOW
