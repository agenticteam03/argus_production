"""Action card and service card data structures and loader (ACR-0019 §3.4).

Service cards declare who owns a service, what safe actions are permitted, and what is never allowed.
Action cards declare preconditions, routes, verify signals, rollbacks, and sources.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml

from argus.actions.preconditions import evaluate_precondition


@dataclass(frozen=True)
class ServiceCard:
    role: str
    kind: str  # stateless | stateful | proxy | database
    owner: str
    criticality: str  # low | medium | high
    data: str  # ephemeral | persistent
    safe_actions: list[str]
    never: list[str]
    allowed_networks: list[str] = field(default_factory=list)
    verify: dict[str, Any] = field(default_factory=dict)
    quirks: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServiceCard:
        return cls(
            role=str(data.get("role", "")),
            kind=str(data.get("kind", "stateless")),
            owner=str(data.get("owner", "")),
            criticality=str(data.get("criticality", "low")),
            data=str(data.get("data", "ephemeral")),
            safe_actions=list(data.get("safe_actions", [])),
            never=list(data.get("never", [])),
            allowed_networks=list(data.get("allowed_networks", [])),
            verify=dict(data.get("verify", {})),
            quirks=list(data.get("quirks", [])),
        )


@dataclass(frozen=True)
class ActionCard:
    name: str
    model_name: str
    executor: str
    route: str
    parameters: dict[str, Any]
    preconditions: list[str]
    useful_when: list[str]
    not_useful_when: list[str]
    verify: dict[str, Any]
    rollback: str
    sources: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionCard:
        return cls(
            name=str(data["name"]),
            model_name=str(data["model_name"]),
            executor=str(data.get("executor", "action-gateway")),
            route=str(data.get("route", "")),
            parameters=dict(data.get("parameters", {})),
            preconditions=list(data.get("preconditions", [])),
            useful_when=list(data.get("useful_when", [])),
            not_useful_when=list(data.get("not_useful_when", [])),
            verify=dict(data.get("verify", {})),
            rollback=str(data.get("rollback", "")),
            sources=list(data.get("sources", [])),
        )

    def check_preconditions(self, context: dict[str, Any]) -> bool:
        """Evaluates all preconditions against the observation context using safe AST evaluation."""
        for expr in self.preconditions:
            if not evaluate_precondition(expr, context):
                return False
        return True


def load_action_cards(directory: Path | str) -> dict[str, ActionCard]:
    """Loads all .yaml action cards from a directory."""
    dir_path = Path(directory)
    cards: dict[str, ActionCard] = {}
    if not dir_path.is_dir():
        return cards

    for yaml_path in sorted(dir_path.glob("*.yaml")):
        content = yaml_path.read_text(encoding="utf-8")
        raw = yaml.safe_load(content)
        if isinstance(raw, dict) and "name" in raw and "model_name" in raw:
            card = ActionCard.from_dict(raw)
            cards[card.name] = card

    return cards
