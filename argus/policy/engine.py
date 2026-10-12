"""Policy engine over the versioned policy data file (v1.8 §13.1; lab: profile G-001, safety class OP-003).

Imports domain only. The rules themselves live in config/policy.yaml.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from argus.domain.model import TargetRef
from argus.policy.inspection import InspectionPolicy


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    rule: str
    reason: str


class PolicyEngine:
    def __init__(self, data: dict, raw_text: str):
        if data.get("profile") not in {"lab", "production"}:
            raise ValueError("policy.yaml must declare profile: lab | production")
        self.profile: str = data["profile"]
        self.max_tool_level: int = int(data.get("max_tool_level", 1))
        self.capabilities: dict[str, dict] = data.get("capabilities", {}) or {}
        self.allowed_safety_classes: set[str] = set(data.get("allowed_safety_classes",
                                                             ["READ_ONLY_SAFE", "READ_ONLY_SENSITIVE"]))
        self.write_gate_open: list = data.get("write_gate", {}).get("open", []) or []
        if self.write_gate_open:
            raise ValueError("v1.8-lab is read-only: write_gate.open must be empty")
        # T-0019 batch 3a: the inspection policy (§4.7); arbitrary_exec: true or a malformed section refuses startup
        self.inspection = InspectionPolicy.from_data(data.get("inspection"))
        self.version = hashlib.sha256(raw_text.encode()).hexdigest()

    def capability_known(self, name: str) -> bool:
        return name in self.capabilities

    def check(self, *, capability: str, level: int, safety_class: str, target: TargetRef,
              incident_scope: set[TargetRef], used_in_incident: int,
              arguments: dict | None = None) -> PolicyDecision:
        """Fail closed. Called after a concrete capability and arguments were chosen, before execution."""
        entry = self.capabilities.get(capability)
        if entry is None:
            return PolicyDecision(False, "allowlist", f"{capability} has no policy entry")
        if level > self.max_tool_level:
            return PolicyDecision(False, "max_tool_level", f"level {level} > {self.max_tool_level}")
        if safety_class not in self.allowed_safety_classes:
            return PolicyDecision(False, "safety_class", f"{safety_class} not allowed in profile {self.profile}")
        if target not in incident_scope:
            return PolicyDecision(False, "incident_scope", f"{target} is outside this incident's scope")
        limit = int(entry.get("max_per_incident", 10))
        if used_in_incident >= limit:
            return PolicyDecision(False, "max_per_incident", f"{capability} used {used_in_incident}/{limit}")
        inspected = self.inspection.allows(target, capability, arguments)   # files, logs, processes (§4.7)
        if not inspected.allowed:
            return PolicyDecision(False, "inspection", inspected.reason)
        return PolicyDecision(True, f"allow:{capability}", "allowed")
