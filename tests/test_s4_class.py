from pathlib import Path
from types import SimpleNamespace

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_worker_stalled_requires_no_processing_old_progress_and_backlog():
    from argus.detectors.classes import worker_stalled

    def detect(rate, depth, age):
        return worker_stalled(SimpleNamespace(values={
            "jobs_processed_rate": rate,
            "queue_depth": depth,
            "worker_last_processed_age_s": age,
        }))

    assert detect(0, 11, 180).matched
    assert not detect(0.2, 11, 240).matched
    assert not detect(0, 10, 240).matched
    assert not detect(0, 11, 179).matched


def test_worker_stalled_incident_signal_list_validates_at_startup():
    from argus.application.incident_metrics import SignalList
    from argus.detectors.classes import CLASSES

    signals = yaml.safe_load((ROOT / "config/signals.yaml").read_text(encoding="utf-8"))
    data = yaml.safe_load((ROOT / "config/ui-incident-signals.yaml").read_text(encoding="utf-8"))
    signal_list = SignalList.from_data(data, set(signals), {item.name for item in CLASSES})
    entries = signal_list.for_class("worker_stalled")
    assert [item.signal for item in entries] == [
        "jobs_processed_rate", "queue_depth", "worker_last_processed_age_s"
    ]
    assert [item.fired for item in entries] == [True, True, True]


def test_worker_stalled_scrape_alert_and_inventory_contract():
    signals = yaml.safe_load((ROOT / "config/signals.yaml").read_text(encoding="utf-8"))
    assert 'rate(argus_lab_jobs_processed_total' in signals["jobs_processed_rate"]
    assert '[5m]' in signals["jobs_processed_rate"]
    assert 'argus_lab_queue_depth' in signals["queue_depth"]
    assert 'time() - argus_lab_last_processed_timestamp_seconds' in signals["worker_last_processed_age_s"]

    from argus.policy.routing import Routing
    routing = yaml.safe_load((ROOT / "config/routing.yaml").read_text(encoding="utf-8"))
    assert Routing.from_data(routing, {"availability", "database", "dependency", "platform", "saturation", "stability"}) \
        .target(family="stability", alertname="WorkerStalled") == "channel:operators"

    prom = yaml.safe_load((ROOT / "deploy/monitoring/prometheus-vm-166.yml").read_text(encoding="utf-8"))
    job = next(item for item in prom["scrape_configs"] if item["job_name"] == "argus-lab-jobworker")
    assert job["static_configs"][0]["targets"] == ["argus-lab-jobworker:8080"]
    assert job["static_configs"][0]["labels"] == {"argus_host": "vm-166", "container": "argus-lab-jobworker"}

    alerts = yaml.safe_load((ROOT / "deploy/monitoring/alerts.yml").read_text(encoding="utf-8"))
    alert = next(rule for group in alerts["groups"] for rule in group["rules"]
                 if rule.get("alert") == "WorkerStalled")
    assert "last_processed_timestamp_seconds" in alert["expr"] and "> 180" in alert["expr"]
    assert "argus_lab_queue_depth" in alert["expr"] and "> 10" in alert["expr"]
    assert "deriv(" in alert["expr"] and "[3m]" in alert["expr"] and "> 0" in alert["expr"]

    inventory = yaml.safe_load((ROOT / "config/inventory.yaml").read_text(encoding="utf-8"))
    worker = next(item for item in inventory["targets"] if item["ref"] == "vm-166/container:argus-lab-jobworker")
    assert worker["depends_on"] == ["vm-166/container:argus-lab-cache", "vm-166/container:argus-lab-db"]
    assert worker["service"]["role"] == "worker" and worker["service"]["kind"] == "stateless"
    assert "container.restart" in worker["service"]["safe_actions"]
    assert "container.stop" in worker["service"]["never"]
    ports = {item["ref"]: item["tcp_ports"] for item in inventory["targets"] if "tcp_ports" in item}
    assert ports["vm-166/container:argus-lab-cache"] == [6379]
    assert ports["vm-166/container:argus-lab-db"] == [5432]
    monitoring = yaml.safe_load((ROOT / "deploy/monitoring/compose.monitoring.yml").read_text(encoding="utf-8"))
    assert set(monitoring["services"]["argus-v18-prometheus"]["networks"]) == {"argus-v18-mon", "argus-lab-app"}
