"""Action card and service card data structures and loader (ACR-0019 §3.4).

Service cards declare who owns a service, what safe actions are permitted, and what is never allowed.
Action cards declare preconditions, routes, verify signals, rollbacks, and sources.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml

from argus.actions.preconditions import evaluate_precondition
from argus.actions.catalog import ACTION_ROUTES, get_action_spec
from argus.domain.service_card import ServiceCard as ServiceCard

_ACTION_CARD_FIELDS = frozenset({
    "name", "model_name", "executor", "route", "parameters", "identity_fields", "preconditions",
    "useful_when", "not_useful_when", "verify", "rollback", "sources",
})
_OPTIONAL_CARD_FIELDS = frozenset({"verify_by_role"})
_CHECK_OPS = frozenset({"==", ">", ">=", "<", "<="})


def _check_verify(file_name: str, label: str, verify: Any) -> None:
    """`verify` is one check (`signal`, `expected`) or `checks: [{signal, expected, op?}, ...]`, all in `window_sec`."""
    if not isinstance(verify, dict):
        raise ValueError(f"{file_name}: {label} must be a mapping")
    window = verify.get("window_sec")
    if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
        raise ValueError(f"{file_name}: {label} needs a positive window_sec")
    if "checks" not in verify:
        if not isinstance(verify.get("signal"), str) or not verify["signal"] or "expected" not in verify:
            raise ValueError(f"{file_name}: {label} needs a signal, expected value and positive window_sec")
        return
    if "signal" in verify or "expected" in verify:
        raise ValueError(f"{file_name}: {label} gives either checks or one signal, not both")
    checks = verify["checks"]
    if not isinstance(checks, list) or not checks:
        raise ValueError(f"{file_name}: {label} checks must be a non-empty list")
    for check in checks:
        if (not isinstance(check, dict) or check.keys() - {"signal", "expected", "op"}
                or not isinstance(check.get("signal"), str) or not check["signal"] or "expected" not in check
                or check.get("op", "==") not in _CHECK_OPS):
            raise ValueError(f"{file_name}: {label} has an invalid check")


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
    identity_fields: list[str] = field(default_factory=list)
    verify_by_role: dict[str, dict[str, Any]] = field(default_factory=dict)

    def _verify_for(self, role: str | None) -> dict[str, Any]:
        return self.verify_by_role.get(role or "", self.verify)

    def verify_checks(self, role: str | None = None) -> list[dict[str, Any]]:
        """The checks that must all hold, one `{signal, op, expected}` each; a single-signal card gives one."""
        verify = self._verify_for(role)
        checks = verify.get("checks") or [{"signal": verify["signal"], "expected": verify["expected"]}]
        return [{"signal": c["signal"], "op": c.get("op", "=="), "expected": c["expected"]} for c in checks]

    def verify_window(self, role: str | None = None) -> int:
        return int(self._verify_for(role)["window_sec"])

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
            identity_fields=list(data.get("identity_fields", [])),
            verify_by_role={str(k): dict(v) for k, v in dict(data.get("verify_by_role", {})).items()},
        )

    def check_preconditions(self, context: dict[str, Any]) -> bool:
        """Evaluates all preconditions against the observation context using safe AST evaluation."""
        for expr in self.preconditions:
            if not evaluate_precondition(expr, context):
                return False
        return True


_STRING_SOURCES = frozenset({"declared_networks"})


def _check_string_parameter(file_name: str, parameter: str, bounds: dict[str, Any]) -> None:
    """A string parameter is never free text: it names a closed source (`enum_from`) or a regex (`pattern`)."""
    extra = bounds.keys() - {"type", "enum_from", "pattern"}
    source, pattern = bounds.get("enum_from"), bounds.get("pattern")
    if extra or (source is None) == (pattern is None):
        raise ValueError(f"{file_name}: {parameter} needs exactly one of enum_from or pattern")
    if source is not None and source not in _STRING_SOURCES:
        raise ValueError(f"{file_name}: {parameter} has an unknown enum_from")
    if pattern is not None:
        try:
            if not isinstance(pattern, str) or not pattern:
                raise re.error("empty")
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"{file_name}: {parameter} has an invalid pattern") from exc


def load_action_cards(directory: Path | str) -> dict[str, ActionCard]:
    """Loads all .yaml action cards from a directory."""
    dir_path = Path(directory)
    cards: dict[str, ActionCard] = {}
    if not dir_path.is_dir():
        return cards

    for yaml_path in sorted(dir_path.glob("*.yaml")):
        content = yaml_path.read_text(encoding="utf-8")
        raw = yaml.safe_load(content)
        if not isinstance(raw, dict):
            raise ValueError(f"{yaml_path.name}: action card must be a mapping")
        missing = _ACTION_CARD_FIELDS - raw.keys()
        extra = raw.keys() - _ACTION_CARD_FIELDS - _OPTIONAL_CARD_FIELDS
        if missing or extra:
            detail = []
            if missing:
                detail.append(f"missing {', '.join(sorted(missing))}")
            if extra:
                detail.append(f"unexpected {', '.join(sorted(extra))}")
            raise ValueError(f"{yaml_path.name}: action card fields are invalid: {'; '.join(detail)}")
        for field_name in ("name", "model_name", "executor", "route", "rollback"):
            if not isinstance(raw[field_name], str) or not raw[field_name]:
                raise ValueError(f"{yaml_path.name}: {field_name} must be a non-empty string")
        for field_name in ("identity_fields", "preconditions", "useful_when", "not_useful_when", "sources"):
            if not isinstance(raw[field_name], list) or not all(isinstance(value, str) and value for value in raw[field_name]):
                raise ValueError(f"{yaml_path.name}: {field_name} must be a list of non-empty strings")
        if not raw["identity_fields"] or not raw["preconditions"] or not raw["sources"]:
            raise ValueError(f"{yaml_path.name}: identity_fields, preconditions and sources must not be empty")
        if not isinstance(raw["parameters"], dict):
            raise ValueError(f"{yaml_path.name}: parameters must be a mapping")
        _check_verify(yaml_path.name, "verify", raw["verify"])
        by_role = raw.get("verify_by_role", {})
        if not isinstance(by_role, dict) or not all(isinstance(role, str) and role for role in by_role):
            raise ValueError(f"{yaml_path.name}: verify_by_role must map a role to a verify block")
        for role, role_verify in by_role.items():
            _check_verify(yaml_path.name, f"verify_by_role.{role}", role_verify)
        card = ActionCard.from_dict(raw)
        spec = get_action_spec(card.name)
        if card.model_name != spec.model_name or card.route != ACTION_ROUTES.get(card.name):
            raise ValueError(f"{yaml_path.name}: action name, model name or route is not reviewed")
        if card.executor != "action-gateway":
            raise ValueError(f"{yaml_path.name}: action card is incomplete")
        for expr in card.preconditions:
            evaluate_precondition(expr, {})  # parse every reviewed guard before the app starts
        for parameter, bounds in card.parameters.items():
            if isinstance(bounds, dict) and bounds.get("type") == "str":
                _check_string_parameter(yaml_path.name, parameter, bounds)
                continue
            if (not isinstance(bounds, dict) or bounds.get("type") != "int"
                    or not isinstance(bounds.get("min"), int) or isinstance(bounds.get("min"), bool)
                    or not isinstance(bounds.get("max"), int) or isinstance(bounds.get("max"), bool)
                    or bounds["min"] < 0 or bounds["min"] > bounds["max"]):
                raise ValueError(f"{yaml_path.name}: {parameter} needs integer bounds")
        if card.name in cards:
            raise ValueError(f"{yaml_path.name}: duplicate action {card.name}")
        cards[card.name] = card

    return cards
