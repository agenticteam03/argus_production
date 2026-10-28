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
    for values in ((float("nan"), 11, 240), (0, float("nan"), 240), (0, 11, float("nan"))):
        result = detect(*values)
        assert not result.matched
        assert result.findings and "unknown, not healthy" in result.findings[0]


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
    assert worker["depends_on"] == ["vm-166/container:argus-lab-cache"]
    assert worker["service"]["role"] == "worker" and worker["service"]["kind"] == "stateless"
    assert "container.restart" in worker["service"]["safe_actions"]
    assert "container.stop" in worker["service"]["never"]
    ports = {item["ref"]: item["tcp_ports"] for item in inventory["targets"] if "tcp_ports" in item}
    assert ports["vm-166/container:argus-lab-cache"] == [6379]
    assert ports["vm-166/container:argus-lab-db"] == [5432]
    monitoring = yaml.safe_load((ROOT / "deploy/monitoring/compose.monitoring.yml").read_text(encoding="utf-8"))
    assert set(monitoring["services"]["argus-v18-prometheus"]["networks"]) == {"argus-v18-mon"}


def test_the_capability_catalogue_names_worker_stalled_as_an_incident_class():
    """TASK-69: `AnomalyArgs.incident_class` must accept every registered class, `worker_stalled` included."""
    from typing import get_args

    from argus.capabilities.catalog import IncidentClassName
    from argus.detectors.classes import CLASSES

    assert "worker_stalled" in get_args(IncidentClassName)
    assert set(get_args(IncidentClassName)) == {spec.name for spec in CLASSES}


def test_worker_stalled_baseline_reads_only_the_worker_and_declared_cache():
    from argus.detectors.classes import CLASSES
    from argus.domain.model import TargetRef
    from argus.orchestration.strategies import BaselineStrategy

    worker = TargetRef.parse("vm-166/container:argus-lab-jobworker")
    cache = TargetRef.parse("vm-166/container:argus-lab-cache")
    cls = next(spec for spec in CLASSES if spec.name == "worker_stalled")
    view = SimpleNamespace(incident_class=cls, incident=SimpleNamespace(target=worker),
                           scope=[cache, worker], offered_specs=[])
    calls = BaselineStrategy().plan(view)
    assert [(call.name, call.arguments["target"]) for call in calls] == [
        ("container.status", str(worker)), ("container.status", str(cache)),
    ]


def test_worker_stalled_baseline_attributes_only_observed_cache_failure():
    from argus.detectors.classes import CLASSES
    from argus.domain.model import TargetRef
    from argus.orchestration.strategies import BaselineStrategy

    worker = TargetRef.parse("vm-166/container:argus-lab-jobworker")
    cache = TargetRef.parse("vm-166/container:argus-lab-cache")
    cls = next(spec for spec in CLASSES if spec.name == "worker_stalled")

    def evidence(capability, text):
        return SimpleNamespace(status="ok", capability=capability, model_text=text)

    running_worker = evidence("container.status", f"{worker}: state=running health=healthy")
    running_cache = evidence("container.status", f"{cache}: state=running health=healthy")
    stopped_cache = evidence("container.status", f"{cache}: state=exited health=unknown")
    broken_link = evidence("network.link_states", "- argus-lab-jobworker -> argus-lab-cache: broken since 12:00 UTC")

    def decide(items):
        view = SimpleNamespace(incident_class=cls, incident=SimpleNamespace(target=worker),
                               scope=[worker, cache], evidence=items)
        return BaselineStrategy()._worker_stalled(view, [item for item in items if item.status == "ok"])

    assert decide([stopped_cache]) is None  # worker state is unknown, not evidence of a cause
    diagnosis, root = decide([running_worker, stopped_cache])
    assert root == str(cache) and "exited" in diagnosis
    diagnosis, root = decide([running_worker, running_cache, broken_link])
    assert root == str(cache) and "broken" in diagnosis


def test_worker_stalled_blames_the_live_worker_only_when_it_runs_and_its_cache_and_link_are_healthy():
    """S4: a running process that does not consume, with a healthy declared cache and an unbroken link, is RB-022's
    "process alive, not consuming" cause. Missing or unknown evidence about the cache is not health."""
    from argus.detectors.classes import CLASSES
    from argus.domain.model import TargetRef
    from argus.orchestration.strategies import BaselineStrategy

    worker = TargetRef.parse("vm-166/container:argus-lab-jobworker")
    cache = TargetRef.parse("vm-166/container:argus-lab-cache")
    cls = next(spec for spec in CLASSES if spec.name == "worker_stalled")

    def evidence(capability, text):
        return SimpleNamespace(status="ok", capability=capability, model_text=text)

    running_worker = evidence("container.status", f"{worker}: state=running health=healthy")
    running_cache = evidence("container.status", f"{cache}: state=running health=healthy")
    ok_link = evidence("network.link_states", "- argus-lab-jobworker -> argus-lab-cache: ok since 12:00 UTC")

    def decide(items):
        view = SimpleNamespace(incident_class=cls, incident=SimpleNamespace(target=worker),
                               scope=[worker, cache], evidence=items)
        return BaselineStrategy()._worker_stalled(view, [item for item in items if item.status == "ok"])

    diagnosis, root = decide([running_worker, running_cache])
    assert root == str(worker) and "not consuming" in diagnosis
    assert decide([running_worker, running_cache, ok_link])[1] == str(worker)
    assert decide([running_worker]) is None                    # the cache was never read: unknown is not healthy
    assert decide([running_cache]) is None                     # the worker was never read


def test_rb_022_offers_a_worker_restart_only_through_a_reviewed_card_and_a_running_worker():
    from argus.actions.incident import ActionPolicy

    policy = ActionPolicy.from_paths(ROOT / "config", ROOT / "argus" / "runbooks")
    [action] = policy.runbook_actions["RB-022"]
    assert (action.action, action.target_role, action.service_role) == ("container.restart", "root_cause", "worker")
    assert "RB-022" in policy.cards["container.restart"].sources
    text = (ROOT / "argus" / "runbooks" / "RB-022-worker-stalled.md").read_text(encoding="utf-8")
    assert "evidence is preserved" in text and "approval" in text      # the safety wording stays
