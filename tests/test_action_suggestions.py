"""Tests for action suggestion generation, basis computation, and SC-03 exit proof (ACR-0019 §3.3, §3.5).

Phase 17 Exit proof:
SC-03 suggests 'start the cache' and never 'restart argus-lab-api'.
The basis is computed by code from cited grounds; the model never declares it.
"""
from __future__ import annotations

import pytest

from argus.actions.cards import (
    ActionCard,
    ServiceCard,
)
from argus.actions.risk import RiskColor, RiskTable
from argus.actions.suggestions import (
    ActionSuggestion,
    Basis,
    compute_basis,
    evaluate_candidate_actions,
    suggest_action,
)
from argus.domain.model import TargetRef


@pytest.fixture()
def risk_table(tmp_path) -> RiskTable:
    content = """
version: 1
matrix:
  container.start:
    stateless: green
    stateful: amber
    proxy: green
    database: amber
  container.restart:
    stateless: green
    stateful: amber
    proxy: amber
    database: forbidden
  container.stop:
    stateless: amber
    stateful: red
    proxy: red
    database: forbidden
"""
    yaml_file = tmp_path / "risk.yaml"
    yaml_file.write_text(content.strip(), encoding="utf-8")
    return RiskTable.from_yaml(yaml_file)


@pytest.fixture()
def action_cards() -> dict[str, ActionCard]:
    return {
        "container.start": ActionCard(
            name="container.start",
            model_name="start_container",
            executor="action-gateway",
            route="/containers/{name}/start",
            parameters={"timeout": "int"},
            preconditions=['status == "exited" or status == "stopped"'],
            useful_when=["Container is offline or stopped"],
            not_useful_when=["Container is already running"],
            verify={"signal": "up", "expected": 1, "window_sec": 30},
            rollback="container.stop",
            sources=["RB-003"],
        ),
        "container.restart": ActionCard(
            name="container.restart",
            model_name="restart_container",
            executor="action-gateway",
            route="/containers/{name}/restart",
            parameters={"timeout": "int"},
            preconditions=['status == "running" or status == "restarting"'],
            useful_when=["Container is hung"],
            not_useful_when=["Victim container of an external dependency outage (RB-003)"],
            verify={"signal": "up", "expected": 1, "window_sec": 60},
            rollback="none",
            sources=["RB-001"],
        ),
        "container.stop": ActionCard(
            name="container.stop",
            model_name="stop_container",
            executor="action-gateway",
            route="/containers/{name}/stop",
            parameters={"timeout": "int"},
            preconditions=['status == "running"'],
            useful_when=["Container is leaking"],
            not_useful_when=["Essential service"],
            verify={"signal": "up", "expected": 0, "window_sec": 30},
            rollback="container.start",
            sources=["RB-004"],
        ),
    }


def test_basis_computed_strictly_by_code():
    assert compute_basis(["RB-003"]) == Basis.runbook
    assert compute_basis(["mem-20261020-01"]) == Basis.memory
    assert compute_basis(["ref-docker-docs-start"]) == Basis.reference
    assert compute_basis(["op-manual-override"]) == Basis.operator
    assert compute_basis(["unverified_external_url"]) == Basis.none
    assert compute_basis([]) == Basis.none


def test_suggest_action_is_strictly_read_only_text():
    s = suggest_action(
        target=TargetRef.parse("vm-166/container:argus-lab-cache"),
        text="Cache is down; execute container.start after verifying memory limit.",
        closest_capability="container.start",
        grounds=["RB-003"],
    )
    assert isinstance(s, ActionSuggestion)
    assert s.is_executable is False
    assert s.closest_capability == "container.start"
    assert s.basis == Basis.runbook
    assert "start the cache" in s.text.lower() or "container.start" in s.text


def test_sc03_exit_proof_suggests_start_cache_and_never_restart_api(risk_table, action_cards):
    """Exit proof (Phase 17):

    In SC-03, Argus diagnoses that the root cause is the offline cache.
    Evaluating candidate actions on the root cause (argus-lab-cache) suggests container.start.
    Evaluating candidate actions on the victim (argus-lab-api) forbids/rejects container.restart.
    """
    cache_ref = TargetRef.parse("vm-166/container:argus-lab-cache")
    cache_service = ServiceCard(
        role="cache",
        kind="stateless",
        owner="platform",
        criticality="low",
        data="ephemeral",
        safe_actions=["container.start", "container.restart"],
        never=["container.stop"],
    )
    cache_obs = {"status": "exited", "exit_code": 0}

    # 1. Root cause target (cache): container.start passes preconditions and is suggested
    cache_candidates = evaluate_candidate_actions(
        target=cache_ref,
        service_card=cache_service,
        action_cards=action_cards,
        risk_table=risk_table,
        observations=cache_obs,
        grounds=["RB-003"],
        is_victim=False,
    )
    assert len(cache_candidates) == 1
    assert cache_candidates[0].action == "container.start"
    assert cache_candidates[0].target == cache_ref
    assert cache_candidates[0].risk_color == RiskColor.green
    assert cache_candidates[0].basis == Basis.runbook

    # 2. Victim target (api): running, but victim of dependency outage
    api_ref = TargetRef.parse("vm-166/container:argus-lab-api")
    api_service = ServiceCard(
        role="api",
        kind="stateless",
        owner="platform",
        criticality="medium",
        data="ephemeral",
        safe_actions=["container.start", "container.restart"],
        never=["container.stop"],
    )
    api_obs = {"status": "running"}

    api_candidates = evaluate_candidate_actions(
        target=api_ref,
        service_card=api_service,
        action_cards=action_cards,
        risk_table=risk_table,
        observations=api_obs,
        grounds=["RB-003"],
        is_victim=True,  # Victim of dependency outage (RB-002, RB-003)
    )
    # Restarting victim is explicitly forbidden / rejected
    assert not any(c.action == "container.restart" for c in api_candidates)
    assert len(api_candidates) == 0


def test_candidate_requires_verified_ground_and_closed_catalogue(risk_table, action_cards):
    cache = ServiceCard("cache", "stateless", "platform", "low", "ephemeral",
                        ["container.start", "invented.action"], [])
    ref = TargetRef.parse("vm-166/container:argus-lab-cache")
    assert evaluate_candidate_actions(ref, cache, action_cards, risk_table, {"status": "exited"}) == []
    assert evaluate_candidate_actions(ref, cache, action_cards, risk_table, {"status": "exited"},
                                      grounds=["RB-999"]) == []

    unknown = ActionCard("invented.action", "invented_action", "action-gateway", "/x", {}, [], [], [], {},
                         "none", ["RB-003"])
    permissive = RiskTable({"invented.action": {"stateless": RiskColor.green}})
    assert evaluate_candidate_actions(ref, cache, {"invented.action": unknown}, permissive, {},
                                      grounds=["RB-003"]) == []
