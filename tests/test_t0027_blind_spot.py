"""T-0027: the monitoring blind spot class (ARCHITECTURE §3 `monitoring_blind_spot`, RB-014; phase 7).

A host whose Prometheus reports a scrape target down (`up == 0`) has lost part of its telemetry: the signals that
target feeds come back empty, and an empty signal must never read as healthy (G-007). The class matches on the host
target, before any other host class, with the fixed evidence pack and no model call. The alert
`ArgusScrapeTargetDown` brings it in. When the gate exporter itself is down, detection stays `undiagnosable` (RB-014).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from argus.adapters.outbound.llm import ScriptedLLM
from argus.domain.model import (AlertNotification, IncidentOutcome, IncidentStatus, MetricSnapshot, RequestKind,
                                TargetRef, utcnow)
from test_core import FakeMetrics, incident, make_app  # noqa: F401  (make_app = fixture)

ROOT = Path(__file__).resolve().parents[1]
HOST = "vm-166/host:vm-166"
NODE_DOWN = {HOST: {"scrape_targets_down": 1}}          # node-exporter down: the disk signals are empty


def _yaml(*parts):
    return yaml.safe_load(ROOT.joinpath(*parts).read_text(encoding="utf-8"))


def _snap(**values) -> MetricSnapshot:
    return MetricSnapshot(target=TargetRef.parse(HOST), observed_at=utcnow(), values=values)


# --- the detector ---------------------------------------------------------------------------------------------------
def test_the_detector_matches_when_a_scrape_target_is_down():
    from argus.detectors.classes import monitoring_blind_spot
    r = monitoring_blind_spot(_snap(scrape_targets_down=2))
    assert r.matched and any("2 scrape targets down" in f for f in r.findings)
    assert any("RB-014" in f for f in r.findings)
    assert not monitoring_blind_spot(_snap(scrape_targets_down=0)).matched


def test_the_detector_treats_a_missing_count_as_unknown():
    from argus.detectors.classes import monitoring_blind_spot
    r = monitoring_blind_spot(_snap(scrape_targets_down=None))
    assert not r.matched and any("unknown" in f for f in r.findings)


def test_the_class_is_registered_for_hosts_before_disk_pressure():
    from argus.detectors.classes import classes_for
    host = [c.name for c in classes_for("host")]
    assert host[0] == "monitoring_blind_spot" and "disk_pressure" in host     # unknown comes before any verdict
    spec = next(c for c in classes_for("host") if c.name == "monitoring_blind_spot")
    assert spec.family == "platform" and spec.runbook_ids == ["RB-014"] and spec.strategy == "evidence_pack"
    assert spec.required_signals == {"scrape_targets_down"}
    assert "monitoring_blind_spot" not in [c.name for c in classes_for("container")]


def test_the_signal_counts_the_hosts_scrape_targets_that_are_down():
    sig = _yaml("config", "signals.yaml")["scrape_targets_down"]
    assert sig.startswith('(count(up{argus_host="$host"} == 0) or vector(0))')        # T-0043 adds the missing jobs


# --- the investigation ----------------------------------------------------------------------------------------------
def _no_model(ctx: str):
    raise AssertionError("the blind spot class must not call the model")


def test_a_report_on_a_blind_host_escalates_with_the_evidence_pack_and_no_model(make_app):
    app = make_app(llm=ScriptedLLM(_no_model), metrics=FakeMetrics(NODE_DOWN))
    inc = app.runner.run(incident(app, HOST, reason="ArgusScrapeTargetDown").id)
    assert inc.incident_class == "monitoring_blind_spot"
    assert inc.status == IncidentStatus.escalated and inc.outcome != IncidentOutcome.diagnosed
    caps = [e.capability for e in app.store.list_evidence(inc.id)]
    assert "host.memory" in caps and "host.cpu" in caps                     # the fixed evidence pack


def test_a_health_check_of_a_blind_host_is_not_healthy(make_app):
    app = make_app(metrics=FakeMetrics(NODE_DOWN))
    inc = app.runner.run(incident(app, HOST, request=RequestKind.check, reason="scheduled check").id)
    assert inc.outcome != IncidentOutcome.no_incident and inc.incident_class == "monitoring_blind_spot"


def test_a_host_with_every_scrape_target_up_is_not_a_blind_spot(make_app):
    app = make_app(metrics=FakeMetrics({HOST: {"scrape_targets_down": 0, "host_disk_used_ratio_5m": 0.3,
                                                "host_disk_hours_to_full": None}}))
    inc = app.runner.run(incident(app, HOST, request=RequestKind.check, reason="scheduled check").id)
    assert inc.outcome == IncidentOutcome.no_incident


# --- the alert ------------------------------------------------------------------------------------------------------
def test_the_scrape_target_down_alert():
    rules = _yaml("deploy", "monitoring", "alerts.yml")["groups"][0]["rules"]
    a = next(r for r in rules if r.get("alert") == "ArgusScrapeTargetDown")
    assert a["expr"] == 'up{job=~"argus-v18-.*"} == 0' and a["for"] == "2m"
    assert "$labels.job" in a["annotations"]["summary"]


def test_two_targets_down_on_one_host_are_one_incident(make_app):
    from argus.application.alerts import HandleAlertNotification
    app = make_app()
    handle = HandleAlertNotification(app.store, app.inventory, FakeMetrics(NODE_DOWN))

    def down(job, fp):
        return AlertNotification(fingerprint=fp, status="firing", starts_at=utcnow(),
                                 labels={"alertname": "ArgusScrapeTargetDown", "argus_host": "vm-166", "job": job},
                                 annotations={"summary": f"scrape target {job} is down"})

    first = handle(down("argus-v18-node-exporter", "fp-node"), source="alertmanager@vm-166")
    second = handle(down("argus-v18-cadvisor", "fp-cadv"), source="alertmanager@vm-166")
    assert first.disposition == "started" and app.store.get_incident(first.incident_id).target == TargetRef.parse(HOST)
    assert second.disposition == "attached" and second.incident_id == first.incident_id
