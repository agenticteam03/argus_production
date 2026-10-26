"""T-0022 (phase 7, ACR-0003): firing alerts reach Argus by the deployment's transport profile.

In `restricted-ssh` (this deployment) the scheduler pulls each host's Argus-owned Alertmanager
(`/api/v2/alerts`) and hands every firing alert to `HandleAlertNotification`, the same use case the push webhook
uses; the identity is the webhook's (`fingerprint + startsAt`, §6.6), so a push and a pull of one alert are one
incident. An alert is only ever attributed to the host whose Alertmanager reported it (no cross-host fallback).
"""
from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import yaml

from argus.domain.model import AlertNotification, RequestKind, TriggerKind
from test_core import make_app  # noqa: F401  (make_app = fixture)

ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def _alert(fp="f1", host="vm-166", container="argus-lab-api", status="firing", name="DependencyProbeFailed",
           starts=T0, **extra) -> AlertNotification:
    labels = {"alertname": name, **({"argus_host": host} if host else {}),
              **({"container": container} if container else {}), **extra}
    return AlertNotification(fingerprint=fp, status=status, starts_at=starts, ends_at=None, labels=labels,
                             annotations={"summary": "a declared dependency is not reachable"})


# --- HandleAlertNotification (application) ---------------------------------------------------------
def test_a_firing_alert_opens_one_incident_with_the_webhook_identity(make_app):
    from argus.application.alerts import HandleAlertNotification
    app = make_app()
    handle = HandleAlertNotification(app.store, app.inventory, app.metrics)
    first = handle(_alert(), source="alertmanager@vm-166")
    again = handle(_alert(), source="alertmanager@vm-166")
    assert first.disposition == "started" and again.disposition == "duplicate"
    assert first.incident_id == again.incident_id
    inc = app.store.get_incident(first.incident_id)
    assert str(inc.target) == "vm-166/container:argus-lab-api"
    assert inc.trigger_kind == TriggerKind.alert and inc.request_kind == RequestKind.report
    assert inc.trigger_id == f"alert:f1:{T0.isoformat()}" and inc.principal == "alertmanager@vm-166"
    assert "DependencyProbeFailed" in inc.reason


def test_a_new_firing_of_the_same_alert_is_a_new_incident(make_app):
    from argus.application.alerts import HandleAlertNotification
    app = make_app()
    handle = HandleAlertNotification(app.store, app.inventory, app.metrics)
    a = handle(_alert(starts=T0), source="alertmanager@vm-166")
    b = handle(_alert(starts=T0.replace(hour=13)), source="alertmanager@vm-166")
    assert a.incident_id != b.incident_id


def test_a_host_level_alert_targets_the_host(make_app):
    from argus.application.alerts import HandleAlertNotification
    app = make_app()
    r = HandleAlertNotification(app.store, app.inventory, app.metrics)(_alert(container=None, name="HostDiskPressure"),
                                                           source="alertmanager@vm-166")
    assert str(app.store.get_incident(r.incident_id).target) == "vm-166/host:vm-166"


def test_resolved_alerts_and_unknown_targets_open_nothing(make_app):
    from argus.application.alerts import HandleAlertNotification
    app = make_app()
    audited, real = [], app.store.append
    app.store.append = lambda rec: audited.append(rec) or real(rec)
    handle = HandleAlertNotification(app.store, app.inventory, app.metrics)
    assert handle(_alert(status="resolved"), source="alertmanager@vm-166").disposition == "ignored"
    refused = handle(_alert(container="not-in-inventory"), source="alertmanager@vm-166")
    assert refused.disposition == "refused" and refused.incident_id is None
    assert any(a.event == "access.alert_target_not_in_inventory" and a.incident_id is None for a in audited)
    assert handle(_alert(host=None), source="alertmanager@vm-166").disposition == "refused"   # no argus_host


def test_the_webhook_goes_through_the_same_use_case(make_app):
    from fastapi.testclient import TestClient
    from argus.adapters.inbound.http import build_webhook
    app = make_app()
    app.alertmanager_token = "am-token-123"
    hook = TestClient(build_webhook(app))
    body = {"alerts": [{"status": "firing", "fingerprint": "f1", "startsAt": T0.isoformat(),
                        "labels": {"alertname": "DependencyProbeFailed", "argus_host": "vm-166",
                                   "container": "argus-lab-api"}, "annotations": {}}]}
    ok = hook.post("/api/v1/alerts", json=body, headers={"Authorization": "Bearer am-token-123"}).json()
    from argus.application.alerts import HandleAlertNotification
    pulled = HandleAlertNotification(app.store, app.inventory, app.metrics)(_alert(), source="alertmanager@vm-166")
    assert ok["accepted"][0]["incident_id"] == pulled.incident_id and pulled.disposition == "duplicate"


# --- the Alertmanager adapter ----------------------------------------------------------------------
def _am_payload(*alerts):
    return [{"fingerprint": fp, "startsAt": T0.isoformat().replace("+00:00", "Z"), "endsAt": None,
             "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
             "labels": {"alertname": "DependencyProbeFailed", "argus_host": host, "container": "argus-lab-api"},
             "annotations": {"summary": "s"}} for fp, host in alerts]


def test_the_alertmanager_source_reads_api_v2_and_keeps_only_its_host():
    from argus.adapters.outbound.alerts_alertmanager import AlertmanagerSource
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_am_payload(("f1", "vm-166"), ("f2", "vm-095")))

    src = AlertmanagerSource({"vm-166": "http://argus-v18-tunnel:18091"},
                             client=httpx.Client(transport=httpx.MockTransport(handler)))
    alerts = src.firing_alerts("vm-166")
    assert "/api/v2/alerts" in seen["url"] and "active=true" in seen["url"] and "silenced=false" in seen["url"]
    assert [a.fingerprint for a in alerts] == ["f1"]                     # f2 says vm-095: dropped, never reassigned
    assert alerts[0].status == "firing" and alerts[0].starts_at == T0


def test_an_unreachable_alertmanager_raises_alerts_unavailable():
    from argus.adapters.outbound.alerts_alertmanager import AlertmanagerSource
    from argus.ports.ports import AlertsUnavailable

    def handler(request):
        raise httpx.ConnectError("refused")

    src = AlertmanagerSource({"vm-166": "http://x:1"}, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(AlertsUnavailable):
        src.firing_alerts("vm-166")
    with pytest.raises(AlertsUnavailable):
        src.firing_alerts("vm-999")                                        # a host with no Alertmanager


# --- ReconcileFiringAlerts -------------------------------------------------------------------------
class FakeSource:
    def __init__(self, by_host):
        self.by_host = by_host

    def firing_alerts(self, host):
        from argus.ports.ports import AlertsUnavailable
        v = self.by_host.get(host)
        if isinstance(v, Exception):
            raise AlertsUnavailable(str(v))
        return v or []

    def active_alerts(self, host):                     # T-0026: nothing silenced, so the active ones are the firing ones
        return self.firing_alerts(host)


def test_reconcile_submits_every_host_and_survives_one_that_is_down(make_app):
    from argus.application.alerts import HandleAlertNotification, ReconcileFiringAlerts
    app = make_app()
    src = FakeSource({"vm-166": [_alert("f1"), _alert("f2", container="argus-lab-cache")],
                      "vm-095": RuntimeError("tunnel down")})
    rec = ReconcileFiringAlerts(src, HandleAlertNotification(app.store, app.inventory, app.metrics), ["vm-095", "vm-166"])
    first = rec.run_once()
    assert first == {"vm-095": "unavailable", "vm-166": {"started": 2}}
    assert rec.run_once()["vm-166"] == {"duplicate": 2}                  # the next pass opens nothing new


# --- configuration and wiring ----------------------------------------------------------------------
def test_the_schedules_file_enables_the_pull():
    from argus.infrastructure.scheduler import load_reconcile
    cfg = load_reconcile((ROOT / "deploy" / "scheduler" / "schedules.yaml").read_text(encoding="utf-8"))
    assert cfg.enabled is True and cfg.every_s == 60
    assert load_reconcile("schedules: []\n").enabled is False             # absent = off (push profiles)
    with pytest.raises(ValueError):
        load_reconcile("reconcile_firing_alerts: {enabled: true, every_s: 5}\n")   # below the 30 s floor


def test_each_host_names_its_alertmanager_outside_the_executors():
    from argus.adapters.outbound.config_adapters import YamlInventory
    inv = YamlInventory((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    am = {h.name: h.alertmanager for h in inv.hosts()}
    assert am == {"vm-095": "http://argus-v18-alertmanager:9093", "vm-166": "http://argus-v18-tunnel:18091"}
    assert all("alertmanager" not in h.executors for h in inv.hosts())   # not an executor: no token, no tools


def test_the_scheduler_stays_a_driver():
    """Rule 15: the scheduler imports no detector, runner, graph or model module (the alert use case is allowed)."""
    tree = ast.parse((ROOT / "argus" / "infrastructure" / "scheduler.py").read_text(encoding="utf-8"))
    names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any(m.startswith(("argus.detectors", "argus.orchestration", "argus.adapters.outbound.llm"))
                   for m in names)


# --- deployment files ------------------------------------------------------------------------------
MON = ROOT / "deploy" / "monitoring"
IMAGES = {"argus-v18-alertmanager": "prom/alertmanager:v0.34.0",
          "argus-v18-node-exporter": "quay.io/prometheus/node-exporter:v1.12.1",
          "argus-v18-cadvisor": "ghcr.io/google/cadvisor:v0.60.5"}


def test_the_monitoring_stack_has_argus_owned_exporters_and_alertmanager():
    svc = yaml.safe_load((MON / "compose.monitoring.yml").read_text(encoding="utf-8"))["services"]
    for name, image in IMAGES.items():
        s = svc[name]
        assert s["image"] == image and s["container_name"] == name
        assert s["mem_limit"] and s.get("cpus") and "ports" not in s           # no host port in the base file
        assert s["networks"] == ["argus-v18-mon"]
    cad = svc["argus-v18-cadvisor"]
    assert all(v.endswith(":ro") for v in cad["volumes"])                    # §4.3: read-only host mounts
    assert "--docker_only=true" in cad["command"]
    loop = yaml.safe_load((MON / "compose.loopback.yml").read_text(encoding="utf-8"))["services"]
    assert loop["argus-v18-alertmanager"]["ports"] == ["127.0.0.1:18091:9093"]   # vm-166: loopback, tunnel only
    join = yaml.safe_load((MON / "compose.core-join.yml").read_text(encoding="utf-8"))["services"]
    assert join["argus-v18-alertmanager"]["networks"] == ["argus-v18-mon", "argus-v18-core",   # vm-095 scheduler
                                                          "argus-v18-sched"]                   # ACR-0018 §18


def test_alertmanager_sends_nothing_off_the_host():
    cfg = yaml.safe_load((MON / "alertmanager.yml").read_text(encoding="utf-8"))
    text = json.dumps(cfg)
    for receiver in ("webhook_configs", "email_configs", "slack_configs", "pagerduty_configs"):
        assert receiver not in text                                           # pull profile: read, never pushed
    assert set(cfg["route"]["group_by"]) == {"alertname", "argus_host", "container"}


@pytest.mark.parametrize("host", ["vm-095", "vm-166"])
def test_prometheus_alerts_to_its_own_alertmanager_and_scrapes_the_exporters(host):
    cfg = yaml.safe_load((MON / f"prometheus-{host}.yml").read_text(encoding="utf-8"))
    am = cfg["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"]
    assert am == ["argus-v18-alertmanager:9093"]
    jobs = {j["job_name"]: j for j in cfg["scrape_configs"]}
    for job, target in (("argus-v18-node-exporter", "argus-v18-node-exporter:9100"),
                        ("argus-v18-cadvisor", "argus-v18-cadvisor:8080")):
        sc = jobs[job]["static_configs"][0]
        assert sc["targets"] == [target] and sc["labels"] == {"argus_host": host}


def test_the_tunnel_forwards_the_vm166_alertmanager():
    text = (ROOT / "deploy" / "vm-095" / "tunnel" / "Dockerfile").read_text(encoding="utf-8")
    assert '"-L", "0.0.0.0:18091:127.0.0.1:18091"' in text


def test_the_new_signals_and_rules_carry_the_host():
    sig = yaml.safe_load((ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
    for name in ("host_disk_used_ratio", "host_cpu_busy_ratio", "host_memory_available_ratio",
                 "container_cpu_throttled_ratio"):
        assert 'argus_host="$host"' in sig[name]
    rules = yaml.safe_load((MON / "alerts.yml").read_text(encoding="utf-8"))["groups"][0]["rules"]
    disk = next(r for r in rules if r["alert"] == "HostDiskPressure")
    assert "argus_host" in disk["expr"] and disk["for"]
