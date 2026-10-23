"""T-0049 S3b: the `add-capability` checker. A missing piece of a new read makes it FAIL, not pass.

The fixtures are the real catalog, policy and classes with one piece changed in memory; nothing is written.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from argus.capabilities.catalog import build_catalog
from argus.detectors.classes import CLASSES
from argus.evaluation.replay import EXECUTORS
from argus.infrastructure.wiring import EXECUTOR_KINDS

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "skills" / "add-capability" / "scripts" / "check_capability.py"
_spec = importlib.util.spec_from_file_location("check_capability", SCRIPT)
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)

NEW = "analysis.new_read"
TESTS = f'S = catalog["{NEW}"]'                                  # a test file that names the new read


def specs_with(**changes):
    """The real catalog plus one new Level 3 read, built from `analysis.anomaly_summary` with `changes` applied."""
    specs = build_catalog()
    base = next(s for s in specs if s.name == "analysis.anomaly_summary")
    new = dataclasses.replace(base, name=NEW, model_name="read_something_new", tags=frozenset({"new_read"}))
    return specs + [dataclasses.replace(new, **changes)]


def policy_with(entry=None):
    pol = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    if entry is not None:
        pol["capabilities"][NEW] = entry
    return pol


def check(specs=None, policy=None, tests=TESTS, classes=CLASSES, allow_offer=False):
    return cc.check(NEW, specs if specs is not None else specs_with(),
                    policy if policy is not None else policy_with({"max_per_incident": 1}),
                    classes, EXECUTOR_KINDS, EXECUTORS, tests, allow_offer=allow_offer)


def test_a_complete_new_read_passes():
    assert check() == []


@pytest.mark.parametrize("entry, why", [
    (None, "no entry in config/policy.yaml"),
    ({}, "no max_per_incident"),
    ({"max_per_incident": 0}, "positive integer"),
    ({"max_per_incident": -1}, "positive integer"),
    ({"max_per_incident": "2"}, "positive integer"),
    ({"max_per_incident": True}, "positive integer"),
])
def test_a_missing_or_bad_per_incident_limit_fails(entry, why):
    # the engine reads a missing limit as 10 (policy/engine.py), so only this check catches it
    assert any(why in p for p in check(policy=policy_with(entry)))


def test_an_initial_class_offer_fails_unless_it_is_the_offer_change():
    offered = specs_with(tags=frozenset({"container"}))             # an existing tag: offered to every container class
    problems = check(specs=offered)
    assert any("offered to" in p and "separate, evaluated change" in p for p in problems)
    assert check(specs=offered, allow_offer=True) == []


def test_a_sensitive_read_needs_its_allowed_fields():
    assert any("allowed_fields" in p for p in check(specs=specs_with(safety_class="READ_ONLY_SENSITIVE")))
    ok = specs_with(safety_class="READ_ONLY_SENSITIVE", allowed_fields=frozenset({"lines"}))
    assert check(specs=ok) == []


@pytest.mark.parametrize("changes, why", [
    ({"safety_class": "MUTATING_LOW_RISK"}, "read safety class"),
    ({"level": 4}, "level"),
    ({"tags": frozenset()}, "no tag"),
    ({"description": " "}, "description"),
    ({"use_when": ""}, "use_when"),
    ({"model_name": "Read-Something"}, "model_name"),
    ({"model_name": "summarize_anomalies"}, "model_name"),          # already the anomaly summary's
    ({"target_kinds": frozenset()}, "target kind"),
    ({"executor": "ssh"}, "unknown executor"),
    ({"executor": "argus_internal"}, "in-worker"),                  # still runs_in tools_child
    ({"runs_in": "worker"}, "in-worker"),                           # still executor prometheus
    ({"max_subcalls": 3}, "combined"),                              # a combined read runs in the worker
])
def test_a_wrong_spec_field_fails(changes, why):
    assert any(why in p for p in check(specs=specs_with(**changes)))


def test_an_executor_replay_cannot_answer_fails():
    assert any("FixtureExecutor" in p for p in cc.check(NEW, specs_with(), policy_with({"max_per_incident": 1}),
                                                        CLASSES, EXECUTOR_KINDS, ("docker_read",), TESTS))


def test_a_read_no_test_names_fails():
    assert any("no test" in p for p in check(tests="nothing about it"))


def test_a_name_not_in_the_catalog_fails():
    assert any("not in the catalog" in p for p in check(specs=build_catalog()))


def run_cli(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8")


def test_every_committed_read_passes_the_structure_checks():
    first = run_cli("--all")
    assert first.returncode == 0, first.stderr
    assert "PASS" in first.stdout
    again = run_cli("--all")                                        # read-only: the same answer the second time
    assert (again.returncode, again.stdout, again.stderr) == (first.returncode, first.stdout, first.stderr)


def test_the_cli_names_one_committed_read_and_refuses_an_unknown_one():
    # analysis.anomaly_summary is offered to container_restart_loop since T-0047 H5 step 2 B (#274)
    assert run_cli("analysis.anomaly_summary").returncode == 1
    assert run_cli("analysis.anomaly_summary", "--allow-offer").returncode == 0
    assert run_cli("container.status").returncode == 1              # offered: only the offer change may do that
    assert run_cli("container.status", "--allow-offer").returncode == 0
    gone = run_cli("analysis.no_such_read")
    assert gone.returncode == 1 and "not in the catalog" in gone.stderr
