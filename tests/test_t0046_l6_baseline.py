"""T-0046 L6: deterministic baselines explicitly consume offered link-state evidence."""
from __future__ import annotations

from types import SimpleNamespace

from argus.capabilities.catalog import build_catalog
from argus.detectors.classes import CLASSES
from argus.domain.model import TargetRef
from argus.orchestration.strategies import BaselineStrategy

LINK_SPEC = next(spec for spec in build_catalog() if spec.name == "network.link_states")
CLASSES_BY_NAME = {cls.name: cls for cls in CLASSES}


def view(class_name, target, scope, evidence=()):
    cls = CLASSES_BY_NAME[class_name]
    incident = SimpleNamespace(target=target)
    return SimpleNamespace(incident_class=cls, incident=incident, scope=scope,
                           offered_specs=[LINK_SPEC], evidence=list(evidence))


def test_link_states_is_offered_only_to_the_three_reviewed_classes():
    offered = sorted(cls.name for cls in CLASSES if LINK_SPEC.tags & cls.tool_tags)
    assert offered == ["dependency_unavailable", "health_check_failed", "nginx_upstream_failure"]


def test_baseline_dependency_and_gateway_plans_read_link_history():
    strategy = BaselineStrategy()
    api = TargetRef.parse("vm-166/container:argus-lab-api")
    cache = TargetRef.parse("vm-166/container:argus-lab-cache")
    nginx = TargetRef.parse("vm-166/container:argus-lab-nginx")

    for class_name, target, peers in (("dependency_unavailable", api, [cache]),
                                      ("nginx_upstream_failure", nginx, [api])):
        calls = strategy.plan(view(class_name, target, [target, *peers]))
        assert any(call.name == "read_link_states" and call.arguments == {
            "target": str(target), "minutes": 30,
        } for call in calls)


def test_health_baseline_observes_dependencies_before_naming_one_as_root_cause():
    strategy = BaselineStrategy()
    api = TargetRef.parse("vm-166/container:argus-lab-api")
    cache = TargetRef.parse("vm-166/container:argus-lab-cache")
    calls = strategy.plan(view("health_check_failed", api, [api, cache]))
    assert any(call.name == "container.status" and call.arguments == {"target": str(cache)} for call in calls)


def test_dependency_baseline_uses_a_broken_link_when_services_are_running():
    api = TargetRef.parse("vm-166/container:argus-lab-api")
    cache = TargetRef.parse("vm-166/container:argus-lab-cache")
    evidence = SimpleNamespace(status="ok", capability="network.link_states",
                               model_text="- argus-lab-api -> argus-lab-cache: broken since 12:00:15 UTC")
    strategy = BaselineStrategy()
    diagnosis, root = strategy._dependency(view("dependency_unavailable", api, [api, cache], [evidence]), [])
    assert root == str(cache)
    assert "link" in diagnosis and "broken" in diagnosis


def test_gateway_baseline_uses_a_broken_upstream_link():
    nginx = TargetRef.parse("vm-166/container:argus-lab-nginx")
    api = TargetRef.parse("vm-166/container:argus-lab-api")
    statuses = [
        SimpleNamespace(status="ok", capability="container.status",
                         model_text=f"{nginx}: state=running health=healthy networks=lab"),
        SimpleNamespace(status="ok", capability="container.status",
                         model_text=f"{api}: state=running health=healthy networks=lab"),
        SimpleNamespace(status="ok", capability="network.link_states",
                         model_text="- argus-lab-nginx -> argus-lab-api: broken since 12:00:15 UTC"),
    ]
    diagnosis, root = BaselineStrategy()._gateway(view("nginx_upstream_failure", nginx, [nginx, api], statuses),
                                                  statuses[:2])
    assert root == str(api)
    assert "link" in diagnosis and "broken" in diagnosis
