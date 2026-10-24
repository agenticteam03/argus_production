"""Reviewed service authorization data kept in the domain layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ServiceCard:
    role: str
    kind: str
    owner: str
    criticality: str
    data: str
    safe_actions: list[str]
    never: list[str]
    allowed_networks: list[str] = field(default_factory=list)
    verify: dict[str, Any] = field(default_factory=dict)
    quirks: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServiceCard:
        if not isinstance(data, dict):
            raise ValueError("service card must be a mapping")
        required = {"role", "kind", "owner", "criticality", "data", "safe_actions", "never"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"service card missing {', '.join(sorted(missing))}")
        for field_name in ("role", "kind", "owner", "criticality", "data"):
            if not isinstance(data[field_name], str) or not data[field_name]:
                raise ValueError(f"service card {field_name} must be a non-empty string")
        if data["kind"] not in {"stateless", "stateful", "proxy", "database"}:
            raise ValueError("service card kind is invalid")
        if data["criticality"] not in {"low", "medium", "high"}:
            raise ValueError("service card criticality is invalid")
        if data["data"] not in {"ephemeral", "persistent"}:
            raise ValueError("service card data class is invalid")
        if not data["role"] or not data["owner"]:
            raise ValueError("service card role and owner are required")
        for field_name in ("safe_actions", "never"):
            if not isinstance(data[field_name], list) or not all(isinstance(x, str) for x in data[field_name]):
                raise ValueError(f"service card {field_name} must be a list of action names")
        if set(data["safe_actions"]) & set(data["never"]):
            raise ValueError("service card safe_actions and never overlap")
        for field_name in ("allowed_networks", "quirks"):
            value = data.get(field_name, [])
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"service card {field_name} must be a list of strings")
        if not isinstance(data.get("verify", {}), dict):
            raise ValueError("service card verify must be a mapping")
        return cls(
            role=str(data.get("role", "")),
            kind=str(data["kind"]),
            owner=str(data.get("owner", "")),
            criticality=str(data["criticality"]),
            data=str(data["data"]),
            safe_actions=list(data.get("safe_actions", [])),
            never=list(data.get("never", [])),
            allowed_networks=list(data.get("allowed_networks", [])),
            verify=dict(data.get("verify", {})),
            quirks=list(data.get("quirks", [])),
        )
