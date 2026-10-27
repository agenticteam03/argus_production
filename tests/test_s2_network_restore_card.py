"""TASK-57: the offline definition of `network.restore` (ACR-0035): card, catalogue, routes, risk row, preconditions,
the string-parameter form of the card loader, the lab's declared networks and the suggestions."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from argus.actions.cards import ServiceCard, load_action_cards
from argus.actions.catalog import (
    ACTION_CATALOGUE,
    ACTION_ROUTES,
    NEVER_OFFERED_ACTIONS,
    get_action_spec,
)
from argus.actions.risk import RiskColor, RiskTable
from argus.actions.suggestions import evaluate_candidate_actions
from argus.domain.model import TargetRef

ROOT = Path(__file__).resolve().parent.parent
API = TargetRef.parse("vm-166/container:argus-lab-api")

WRONG = {"state": "running", "declared_networks": ["argus-lab-app"], "networks": ["argus-lab-iso"],
         "connect_network": "argus-lab-app", "disconnect_network": "argus-lab-iso"}
HEALTHY = {"state": "running", "declared_networks": ["argus-lab-app"], "networks": ["argus-lab-app"],
           "connect_network": "argus-lab-app", "disconnect_network": "argus-lab-iso"}


@pytest.fixture()
def cards():
    return load_action_cards(ROOT / "config/actions")


def _write_card(tmp_path, parameters):
    raw = yaml.safe_load((ROOT / "config/actions/network.restore.yaml").read_text(encoding="utf-8"))
    raw["parameters"] = parameters
    (tmp_path / "network.restore.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    return tmp_path


def test_catalogue_has_one_network_action_and_one_worker_route():
    spec = get_action_spec("network.restore")
    assert spec.model_name == "restore_network" and spec.intent == "network"
    assert "container.network_connect" not in ACTION_CATALOGUE
    assert "container.network_disconnect" not in ACTION_CATALOGUE
    assert ACTION_ROUTES["network.restore"] == "/containers/{name}/network-restore"
    assert not [k for k in vars(__import__("argus.actions.catalog", fromlist=["x"])) if k.startswith("ACTION_ROUTES_")]
    assert "network.restore" not in NEVER_OFFERED_ACTIONS


def test_card_loads_with_string_parameters(cards):
    card = cards["network.restore"]
    assert card.executor == "action-gateway" and card.identity_fields == ["container_id"]
    assert card.parameters["connect_network"]["type"] == "str"
    assert card.parameters["disconnect_network"]["type"] == "str"
    assert card.rollback == "network.restore"
    assert card.verify["signal"] == "link_ok"
    assert set(card.sources) == {"RB-003", "RB-009"}


def test_wrong_network_facts_pass_and_healthy_facts_fail(cards):
    card = cards["network.restore"]
    assert card.check_preconditions(WRONG) is True
    assert card.check_preconditions(HEALTHY) is False
    assert card.check_preconditions({**WRONG, "state": "exited"}) is False


@pytest.mark.parametrize("bad", ["bridge", "host", "none"])
def test_default_networks_are_never_a_parameter(cards, bad):
    card = cards["network.restore"]
    assert card.check_preconditions({**WRONG, "networks": [bad], "disconnect_network": bad}) is False
    assert card.check_preconditions({**WRONG, "declared_networks": [bad], "connect_network": bad}) is False


def test_undeclared_connect_and_declared_disconnect_are_refused(cards):
    card = cards["network.restore"]
    assert card.check_preconditions({**WRONG, "connect_network": "other"}) is False
    swapped = {**WRONG, "networks": ["argus-lab-iso", "argus-lab-app"],
               "connect_network": "argus-lab-iso", "disconnect_network": "argus-lab-app"}
    assert card.check_preconditions(swapped) is False
    assert card.check_preconditions({k: v for k, v in WRONG.items() if k != "networks"}) is False


def test_the_target_keeps_a_declared_network_after_the_action(cards):
    assert cards["network.restore"].check_preconditions({**WRONG, "declared_networks": []}) is False


def test_string_parameter_forms(tmp_path):
    ok = {"connect_network": {"type": "str", "enum_from": "declared_networks"},
          "disconnect_network": {"type": "str", "pattern": "^argus-lab-[a-z]+$"}}
    assert "network.restore" in load_action_cards(_write_card(tmp_path, ok))


@pytest.mark.parametrize("bounds", [
    {"type": "str"},                                          # an unconstrained string is refused
    {"type": "str", "enum_from": "everything"},
    {"type": "str", "pattern": "("},
    {"type": "str", "pattern": ""},
    {"type": "str", "enum_from": "declared_networks", "min": 1},
    {"type": "float", "enum_from": "declared_networks"},
])
def test_bad_string_parameters_are_refused(tmp_path, bounds):
    params = {"connect_network": bounds, "disconnect_network": {"type": "str", "enum_from": "declared_networks"}}
    with pytest.raises(ValueError):
        load_action_cards(_write_card(tmp_path, params))


def test_int_only_cards_load_as_before(cards):
    assert cards["container.restart"].parameters == {"timeout": {"type": "int", "min": 1, "max": 60}}


def test_int_parameter_without_bounds_is_still_refused(tmp_path):
    with pytest.raises(ValueError, match="integer bounds"):
        load_action_cards(_write_card(tmp_path, {"timeout": {"type": "int"}}))


def test_risk_row():
    table = RiskTable.from_yaml(ROOT / "config/risk.yaml")
    assert table.lookup("network.restore", "stateless") == RiskColor.amber
    assert table.lookup("network.restore", "stateful") == RiskColor.red
    assert table.lookup("network.restore", "proxy") == RiskColor.red
    assert table.lookup("network.restore", "database") == RiskColor.forbidden


def test_lab_containers_declare_their_network():
    from argus.adapters.outbound.config_adapters import YamlInventory
    inv = YamlInventory((ROOT / "config/inventory.yaml").read_text(encoding="utf-8"))
    for name in ("argus-lab-api", "argus-lab-cache", "argus-lab-client", "argus-lab-backend"):
        assert inv.target(TargetRef.parse(f"vm-166/container:{name}")).networks == ["argus-lab-app"]


def _api_card(**kw):
    base = dict(role="api", kind="stateless", owner="platform", criticality="medium", data="ephemeral",
                safe_actions=["network.restore"], never=["container.stop"])
    return ServiceCard(**{**base, **kw})


def _offered(cards, observations, service=None):
    return evaluate_candidate_actions(API, service or _api_card(), cards,
                                      RiskTable.from_yaml(ROOT / "config/risk.yaml"), observations,
                                      grounds=["RB-003"], verified_sources={"RB-003"}, is_victim=False)


def test_suggestions_offer_it_for_the_wrong_network_and_not_for_a_healthy_container(cards):
    offered = _offered(cards, WRONG)
    assert [s.action for s in offered] == ["network.restore"]
    assert offered[0].risk_color == RiskColor.amber and offered[0].is_executable is False
    assert _offered(cards, HEALTHY) == []


def test_suggestions_respect_service_card_and_database_forbidden(cards):
    assert _offered(cards, WRONG, _api_card(safe_actions=["container.start"])) == []
    assert _offered(cards, WRONG, _api_card(never=["network.restore"])) == []
    db = _api_card(role="database", kind="database", criticality="high", data="persistent")
    assert _offered(cards, WRONG, db) == []


def test_unreleased_pair_stays_refused():
    policy = yaml.safe_load((ROOT / "config/policy.yaml").read_text(encoding="utf-8"))
    assert policy["write_gate"]["open"] == []
