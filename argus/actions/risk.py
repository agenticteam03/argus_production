"""Risk evaluation matrix and escalation rules (ACR-0019 §3.7).

Risk levels: green < amber < red < forbidden.
The model never rates risk. The colour is determined by reviewed tables and can only go up.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any
import yaml


class RiskColor(str, Enum):
    green = "green"
    amber = "amber"
    red = "red"
    forbidden = "forbidden"

    def rank(self) -> int:
        return _RANK_BY_COLOR[self]

    @classmethod
    def from_rank(cls, rank: int) -> RiskColor:
        clamped = min(rank, _RANK_BY_COLOR[cls.forbidden])
        return _COLOR_BY_RANK[clamped]

    def elevate(self, levels: int = 1) -> RiskColor:
        if levels <= 0:
            return self
        return self.from_rank(self.rank() + levels)


_RANK_BY_COLOR = {
    RiskColor.green: 0,
    RiskColor.amber: 1,
    RiskColor.red: 2,
    RiskColor.forbidden: 3,
}

_COLOR_BY_RANK = {v: k for k, v in _RANK_BY_COLOR.items()}


class RiskTable:
    """Lookup matrix of (action, target_kind) -> RiskColor."""

    def __init__(self, matrix: dict[str, dict[str, RiskColor]]) -> None:
        self._matrix = matrix

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskTable:
        matrix: dict[str, dict[str, RiskColor]] = {}
        raw_matrix = data.get("matrix", {})
        for action, kinds in raw_matrix.items():
            matrix[action] = {}
            for kind, color_str in kinds.items():
                try:
                    matrix[action][kind] = RiskColor(str(color_str).lower())
                except ValueError:
                    matrix[action][kind] = RiskColor.forbidden
        return cls(matrix)

    @classmethod
    def from_yaml(cls, path: Path | str) -> RiskTable:
        content = Path(path).read_text(encoding="utf-8")
        parsed = yaml.safe_load(content) or {}
        return cls.from_dict(parsed)

    def lookup(self, action: str, target_kind: str) -> RiskColor:
        action_kinds = self._matrix.get(action)
        if not action_kinds:
            return RiskColor.forbidden
        return action_kinds.get(target_kind, RiskColor.forbidden)


def resolve_proposal_risk(
    risk_table: RiskTable,
    action: str,
    target_kind: str,
    criticality: str = "low",
    judge_verdict: str = "agree",
) -> RiskColor:
    """Calculates the proposal risk color, enforcing that color can only go up."""
    base_color = risk_table.lookup(action, target_kind)
    if base_color == RiskColor.forbidden:
        return RiskColor.forbidden

    elevations = 0
    if criticality.lower() == "high":
        elevations += 1

    if judge_verdict.lower() in ("disagree", "doubt"):
        elevations += 1

    return base_color.elevate(elevations)
