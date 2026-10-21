"""ACR-0027 (OP-002 G-001, G-003, G-007): what the code already does, now in ARCHITECTURE §5.4, §12.3 and §13.1.

These pin the text to the code: the policy names a profile or the engine refuses to start; an observation and an
evidence record carry their provenance; a missing metric is None, never 0.
"""
from __future__ import annotations

import pytest
import yaml

from argus.domain.model import EvidenceRecord, MetricSnapshot, Observation, TargetRef
from argus.policy.engine import PolicyEngine
from test_core import ROOT


# --- G-001: the profile ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("profile", [None, "", "staging", "Lab"])
def test_the_engine_refuses_a_missing_or_unknown_profile(profile):
    data = {"max_tool_level": 3, "capabilities": {}}
    if profile is not None:
        data["profile"] = profile
    with pytest.raises(ValueError, match="profile"):
        PolicyEngine(data, yaml.safe_dump(data))


@pytest.mark.parametrize("profile", ["lab", "production"])
def test_the_two_profiles_load(profile):
    data = {"profile": profile, "max_tool_level": 3, "capabilities": {}}
    assert PolicyEngine(data, yaml.safe_dump(data)).profile == profile


def test_the_deployed_policy_names_a_profile():
    data = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    assert data["profile"] in {"lab", "production"}


# --- G-003: provenance --------------------------------------------------------------------------------------------------
def test_an_observation_carries_its_provenance():
    assert {"source_time", "collected_at", "units", "partial", "coverage", "identities"} <= set(Observation.model_fields)
    assert Observation.model_fields["source_time"].default is None


def test_an_evidence_record_carries_its_provenance():
    assert {"source_time", "collected_at", "partial", "truncated", "redactions"} <= set(EvidenceRecord.model_fields)


# --- G-007: unknown is never healthy ------------------------------------------------------------------------------------
def test_a_missing_metric_is_none_never_zero():
    snap = MetricSnapshot(target=TargetRef.parse("vm-166/container:api"), observed_at=None,
                          values={"memory_ratio": None, "restarts_10m": 0.0})
    assert snap.observed_at is None
    assert snap.values["memory_ratio"] is None and snap.values["restarts_10m"] == 0.0
