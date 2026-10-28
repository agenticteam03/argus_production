"""TASK-63 (scenario 1): `analysis.anomaly_summary` is offered to `dependency_unavailable`, so the model can read the
onset order that TASK-50's ranking rule uses (TASK-62 passes it on). No other class gains the read."""
from __future__ import annotations

from argus.capabilities.catalog import build_catalog
from argus.detectors.classes import CLASSES

SUMMARY = {s.name: s for s in build_catalog()}["analysis.anomaly_summary"]


def offered_to():
    return sorted(c.name for c in CLASSES if SUMMARY.tags & c.tool_tags)


def test_dependency_unavailable_is_offered_the_anomaly_summary():
    assert "dependency_unavailable" in offered_to()


def test_no_other_class_gets_it_than_the_restart_and_dependency_classes():
    assert offered_to() == ["container_restart_loop", "dependency_unavailable"]
    assert "health_check_failed" not in offered_to()      # the pinned test does not place it with this class
