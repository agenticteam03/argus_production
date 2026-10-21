"""ACR-0026 (OP-003): one scheme of safety classes for every capability (ARCHITECTURE §12.3).

The registry holds only classes of the five, never FORBIDDEN; a read that returns raw text written by the target's
software (log lines, journal lines, file or configuration contents) or names found on the host is READ_ONLY_SENSITIVE,
and a combined read is as sensitive as its most sensitive sub-read.
"""
from __future__ import annotations

import dataclasses

import pytest
import yaml

from argus.capabilities.catalog import SUBREADS, build_catalog, diagnostic_snapshot, trace_request_path
from argus.capabilities.spec import SAFETY_CLASSES
from argus.domain.model import TargetRef
from test_core import ROOT

# the reads that return the target's own text, or names found on the host; a new one belongs here
RAW_TEXT_READS = {"container.logs", "container.detailed_logs", "container.search_logs", "host.journal",
                  "host.read_file", "host.service_config", "host.directory_sizes"}


def registry_problems(specs) -> list[str]:
    problems = []
    for s in specs:
        if s.safety_class not in SAFETY_CLASSES:
            problems.append(f"{s.name}: unknown class {s.safety_class}")
        elif s.safety_class == "FORBIDDEN":
            problems.append(f"{s.name}: FORBIDDEN is never registered")
        if s.name in RAW_TEXT_READS and s.safety_class != "READ_ONLY_SENSITIVE":
            problems.append(f"{s.name}: returns the target's text, so READ_ONLY_SENSITIVE")
    classes = {s.name: s.safety_class for s in specs}
    for s in specs:
        sensitive = [r for r in SUBREADS.get(s.name, ()) if classes.get(r) == "READ_ONLY_SENSITIVE"]
        if sensitive and s.safety_class != "READ_ONLY_SENSITIVE":
            problems.append(f"{s.name}: combines {', '.join(sensitive)}, so READ_ONLY_SENSITIVE")
    return problems


def test_the_five_classes():
    assert SAFETY_CLASSES == ("READ_ONLY_SAFE", "READ_ONLY_SENSITIVE", "MUTATING_LOW_RISK", "MUTATING_HIGH_RISK",
                              "FORBIDDEN")


def test_the_registry_follows_the_scheme():
    assert registry_problems(build_catalog()) == []


def test_every_raw_text_read_is_registered():
    assert RAW_TEXT_READS <= {s.name for s in build_catalog()}


@pytest.mark.parametrize("name, cls, problem", [
    ("container.status", "FORBIDDEN", "FORBIDDEN is never registered"),
    ("container.status", "DESTRUCTIVE", "unknown class"),
    ("container.detailed_logs", "READ_ONLY_SAFE", "READ_ONLY_SENSITIVE"),
    ("analysis.diagnostic_snapshot", "READ_ONLY_SAFE", "combines container.logs"),
])
def test_a_spec_outside_the_scheme_is_reported(name, cls, problem):
    specs = [dataclasses.replace(s, safety_class=cls) if s.name == name else s for s in build_catalog()]
    found = registry_problems(specs)
    assert len(found) == 1 and found[0].startswith(name) and problem in found[0]


def test_the_policy_allows_no_class_outside_the_scheme():
    policy = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    allowed = set(policy["allowed_safety_classes"])
    assert allowed <= set(SAFETY_CLASSES) - {"FORBIDDEN"}


def test_every_combined_read_declares_its_subreads():
    assert {s.name for s in build_catalog() if s.max_subcalls} == set(SUBREADS)
    assert {r for reads in SUBREADS.values() for r in reads} <= {s.name for s in build_catalog()}


class _Recorder:
    def __init__(self):
        self.names = []

    def read(self, name, target, args):
        self.names.append(name)
        return type("Obs", (), {"status": "ok", "model_text": "ok"})(), None


def test_the_declared_subreads_are_the_ones_called():
    target = TargetRef.parse("vm-166/container:api")
    snap = _Recorder()
    diagnostic_snapshot(None, target, None, snap)
    assert set(snap.names) == set(SUBREADS["analysis.diagnostic_snapshot"])
    trace = _Recorder()
    info = type("Info", (), {"depends_on": [TargetRef.parse("vm-166/container:cache")]})()
    trace_request_path(None, target, info, trace)
    assert set(trace.names) == set(SUBREADS["analysis.trace_request_path"])
