"""OP-014 step 9: tests written from the last 36 timeouts of the mutation runs, judged one by one (mutmut 3.3.1, one
worker, then each remaining one under `MUTANT_UNDER_TEST` without mutmut's time limit): 15 were already detected,
21 survived. These tests pin 13 of them; the 8 left are equivalent (journal entry of 2026-10-22).

They pin the policy's defaults and refusals and two refusals of the read path: a policy without `max_tool_level`
allows level 1 only, a refusal is `False` (not merely falsy) with its reason, a capability whose spec is not a read is
refused before anything runs, and a refusal keeps the target it was asked about.
"""
from __future__ import annotations

import dataclasses

import pytest
import yaml

from argus.policy.engine import PolicyEngine
from test_combined_capabilities import API, OTHER, SPECS, Catalogue, _invoke
from test_op014_mutation_policy_decisions import _check, _engine


def _raw(data):
    return PolicyEngine(data, yaml.safe_dump(data))


def test_a_policy_without_max_tool_level_allows_level_1_only():
    e = _raw({"profile": "lab", "capabilities": {"container.status": {}}})
    assert e.max_tool_level == 1
    assert _check(e, level=1).allowed is True
    d = _check(e, level=2)
    assert (d.allowed, d.rule, d.reason) == (False, "max_tool_level", "level 2 > 1")


def test_a_policy_that_cannot_start_says_exactly_why():
    with pytest.raises(ValueError) as no_profile:
        _raw({"capabilities": {}})
    assert str(no_profile.value) == "policy.yaml must declare profile: lab | production"
    with pytest.raises(ValueError) as gate_open:
        _raw({"profile": "lab", "write_gate": {"open": ["container.restart"]}})
    assert str(gate_open.value) == "v1.8-lab is read-only: write_gate.open must be empty"


def test_a_refusal_is_false_not_merely_falsy_and_names_its_reason():
    unknown = _check(_engine(), capability="host.exec")
    assert unknown.allowed is False
    assert (unknown.rule, unknown.reason) == ("allowlist", "host.exec has no policy entry")
    outside = _check(_engine(), target=OTHER)
    assert outside.allowed is False and outside.rule == "incident_scope"


def test_a_capability_whose_spec_is_not_a_read_is_refused_before_anything_runs():
    write = dataclasses.replace(SPECS["container.status"], name="container.restart", permission="write")
    cat = Catalogue({"container.restart": write})
    inv, ctx, audit, mem = _invoke(cat)
    obs, ref = inv(ctx, "container.restart", {"target": str(API)})
    assert (audit[0].category, audit[0].event) == ("security", "security.unknown_or_write_capability")
    assert (obs.status, obs.error_category) == ("refused", "forbidden") and cat.calls == []


def test_a_bad_target_is_audited_with_the_capability_it_was_asked_for():
    inv, ctx, audit, mem = _invoke(Catalogue())
    inv(ctx, "container.status", {"target": "not a target"})
    assert (audit[0].event, audit[0].policy_rule, audit[0].capability) == (
        "tool.refused", "validation", "container.status")


def test_a_policy_refusal_keeps_its_target_and_tells_the_model_why():
    inv, ctx, audit, mem = _invoke(Catalogue(), scope=(API,))
    obs, ref = inv(ctx, "container.status", {"target": str(OTHER)})
    assert obs.target == OTHER and obs.host == OTHER.host                  # not the incident's target
    assert obs.model_text == f"REFUSED container.status: {OTHER} is outside this incident's scope"
