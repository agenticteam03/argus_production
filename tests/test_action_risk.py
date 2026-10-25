"""Tests for the risk color matrix and level elevation (ACR-0019 §3.7).

Risk colors: green < amber < red < forbidden.
The model never rates risk. The color can only go up.
"""
from __future__ import annotations

import pytest

from argus.actions.risk import (
    RiskColor,
    RiskTable,
    resolve_proposal_risk,
)


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


def test_base_risk_resolution(risk_table: RiskTable):
    # Stateless cache restart is green
    assert risk_table.lookup("container.restart", "stateless") == RiskColor.green
    # Database restart is forbidden
    assert risk_table.lookup("container.restart", "database") == RiskColor.forbidden
    # Stateful container stop is red
    assert risk_table.lookup("container.stop", "stateful") == RiskColor.red


def test_unknown_action_or_target_kind_defaults_to_forbidden(risk_table: RiskTable):
    assert risk_table.lookup("unknown.action", "stateless") == RiskColor.forbidden
    assert risk_table.lookup("container.restart", "unknown_kind") == RiskColor.forbidden


def test_color_can_only_go_up_on_high_criticality(risk_table: RiskTable):
    # Base green raised to amber on high criticality
    resolved = resolve_proposal_risk(
        risk_table=risk_table,
        action="container.restart",
        target_kind="stateless",
        criticality="high",
        judge_verdict="agree",
    )
    assert resolved == RiskColor.amber

    # Base amber raised to red on high criticality
    resolved = resolve_proposal_risk(
        risk_table=risk_table,
        action="container.stop",
        target_kind="stateless",
        criticality="high",
        judge_verdict="agree",
    )
    assert resolved == RiskColor.red


def test_color_raised_on_judge_disagree_or_doubt(risk_table: RiskTable):
    # Base green raised to amber on judge disagree
    resolved = resolve_proposal_risk(
        risk_table=risk_table,
        action="container.restart",
        target_kind="stateless",
        criticality="low",
        judge_verdict="disagree",
    )
    assert resolved == RiskColor.amber

    # High criticality AND judge disagree raises by two levels (green -> amber -> red)
    resolved = resolve_proposal_risk(
        risk_table=risk_table,
        action="container.restart",
        target_kind="stateless",
        criticality="high",
        judge_verdict="disagree",
    )
    assert resolved == RiskColor.red


def test_forbidden_never_lowered(risk_table: RiskTable):
    resolved = resolve_proposal_risk(
        risk_table=risk_table,
        action="container.restart",
        target_kind="database",
        criticality="low",
        judge_verdict="agree",
    )
    assert resolved == RiskColor.forbidden


def test_real_config_risk_yaml_loads_and_protects_database():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    table = RiskTable.from_yaml(root / "config/risk.yaml")
    assert table.lookup("container.restart", "database") == RiskColor.forbidden
    assert table.lookup("container.restart", "stateless") == RiskColor.green
    assert table.lookup("container.start", "stateless") == RiskColor.green
