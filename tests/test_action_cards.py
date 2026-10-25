"""Tests for action cards, service cards, and the closed action catalogue (ACR-0019 §3.3, §3.4).
"""
from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from argus.actions.cards import (
    ActionCard,
    ServiceCard,
    load_action_cards,
)
from argus.actions.catalog import (
    ACTION_CATALOGUE,
    NEVER_OFFERED_ACTIONS,
    get_action_spec,
    is_action_permitted_on_service,
)


def test_closed_catalogue_contains_docker_actions():
    start = get_action_spec("container.start")
    assert start.model_name == "start_container"
    assert start.intent == "start"

    restart = get_action_spec("container.restart")
    assert restart.model_name == "restart_container"
    assert restart.intent == "start"


def test_never_offered_actions_cannot_be_in_catalogue():
    for forbidden in NEVER_OFFERED_ACTIONS:
        assert forbidden not in ACTION_CATALOGUE
        assert not any(spec.name == forbidden or spec.model_name == forbidden for spec in ACTION_CATALOGUE.values())


def test_service_card_safe_actions_and_never_rules():
    db_card = ServiceCard(
        role="database",
        kind="database",
        owner="team-data",
        criticality="high",
        data="persistent",
        safe_actions=[],
        never=["container.restart", "container.stop", "container.pause"],
    )
    # Restarting DB is explicitly forbidden
    assert is_action_permitted_on_service("container.restart", db_card) is False
    assert is_action_permitted_on_service("container.stop", db_card) is False

    cache_card = ServiceCard(
        role="cache",
        kind="stateless",
        owner="team-platform",
        criticality="low",
        data="ephemeral",
        safe_actions=["container.start", "container.restart"],
        never=["container.stop"],
    )
    # Start and restart are allowed on cache; stop is in never
    assert is_action_permitted_on_service("container.start", cache_card) is True
    assert is_action_permitted_on_service("container.restart", cache_card) is True
    assert is_action_permitted_on_service("container.stop", cache_card) is False

    # An action not declared in safe_actions is not permitted
    assert is_action_permitted_on_service("container.pause", cache_card) is False


def test_action_card_preconditions_check():
    card = ActionCard(
        name="container.start",
        model_name="start_container",
        executor="action-gateway",
        route="/containers/{name}/start",
        parameters={"timeout": "int"},
        preconditions=[
            'status == "exited" or status == "stopped"',
        ],
        useful_when=["Container is stopped or crashed"],
        not_useful_when=["Container is already running"],
        verify={"signal": "up", "expected": 1, "window_sec": 30},
        rollback="container.stop",
        sources=["RB-003"],
    )

    # Preconditions satisfied when container is exited
    assert card.check_preconditions({"status": "exited"}) is True
    # Preconditions fail when container is running
    assert card.check_preconditions({"status": "running"}) is False


def test_load_real_action_cards():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    actions_dir = root / "config/actions"
    cards = load_action_cards(actions_dir)
    assert "container.start" in cards
    assert "container.restart" in cards
    assert "container.stop" in cards

    start_card = cards["container.start"]
    assert start_card.name == "container.start"
    assert start_card.check_preconditions({"state": "exited"}) is True
    assert start_card.check_preconditions({"state": "running"}) is False
    assert cards["container.restart"].check_preconditions({"state": "running"}) is True
    assert cards["container.restart"].check_preconditions({"state": "restarting"}) is True
    assert cards["container.stop"].check_preconditions({"state": "running"}) is True


def test_real_inventory_has_service_cards():
    from pathlib import Path
    from argus.adapters.outbound.config_adapters import YamlInventory
    from argus.domain.model import TargetRef

    root = Path(__file__).resolve().parent.parent
    text = (root / "config/inventory.yaml").read_text(encoding="utf-8")
    inv = YamlInventory(text)

    cache_target = inv.target(TargetRef.parse("vm-166/container:argus-lab-cache"))
    assert cache_target is not None
    cache_service = cache_target.service_card()
    assert cache_service is not None
    assert cache_service.role == "cache"
    assert "container.start" in cache_service.safe_actions

    db_target = inv.target(TargetRef.parse("vm-166/container:argus-lab-db"))
    assert db_target is not None
    db_service = db_target.service_card()
    assert db_service is not None
    assert db_service.kind == "database"
    assert "container.restart" in db_service.never


def test_service_card_rejects_missing_or_unsafe_fields():
    with pytest.raises(ValueError, match="missing"):
        ServiceCard.from_dict({"role": "cache", "safe_actions": ["container.start"]})
    with pytest.raises(ValueError, match="mapping"):
        ServiceCard.from_dict([])
    with pytest.raises(ValueError, match="criticality"):
        ServiceCard.from_dict({"role": "cache", "kind": "stateless", "owner": "platform",
                               "criticality": "unknown", "data": "ephemeral",
                               "safe_actions": ["container.start"], "never": []})


def test_action_loader_rejects_unreviewed_route(tmp_path):
    root = Path(__file__).resolve().parent.parent
    raw = yaml.safe_load((root / "config/actions/container.start.yaml").read_text(encoding="utf-8"))
    raw["route"] = "/containers/{name}/exec"
    (tmp_path / "container.start.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="not reviewed"):
        load_action_cards(tmp_path)


def test_action_loader_rejects_incomplete_card(tmp_path):
    root = Path(__file__).resolve().parent.parent
    raw = yaml.safe_load((root / "config/actions/container.start.yaml").read_text(encoding="utf-8"))
    raw.pop("verify")
    (tmp_path / "container.start.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="verify"):
        load_action_cards(tmp_path)


def test_action_loader_rejects_boolean_integer_bounds(tmp_path):
    root = Path(__file__).resolve().parent.parent
    raw = yaml.safe_load((root / "config/actions/container.start.yaml").read_text(encoding="utf-8"))
    raw["parameters"]["timeout"]["min"] = True
    (tmp_path / "container.start.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="integer bounds"):
        load_action_cards(tmp_path)


def test_inventory_rejects_unknown_never_action():
    from argus.adapters.outbound.config_adapters import YamlInventory

    root = Path(__file__).resolve().parent.parent
    raw = yaml.safe_load((root / "config/inventory.yaml").read_text(encoding="utf-8"))
    cache = next(t for t in raw["targets"] if t["ref"] == "vm-166/container:argus-lab-cache")
    cache["service"]["never"] = ["invented.action"]
    with pytest.raises(ValueError, match="unsupported actions"):
        YamlInventory(yaml.safe_dump(raw))
