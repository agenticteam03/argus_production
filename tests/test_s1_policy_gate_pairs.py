"""The write gate accepts only unique, catalogue-backed vm-166 lab pairs."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from argus.policy.engine import PolicyEngine


ROOT = Path(__file__).resolve().parents[1]
POLICY_TEXT = (ROOT / "config/policy.yaml").read_text(encoding="utf-8")
BASE_POLICY = yaml.safe_load(POLICY_TEXT)
CACHE_PAIR = {"capability": "container.start", "target": "vm-166/container:argus-lab-cache"}


def _engine(open_entries):
    data = copy.deepcopy(BASE_POLICY)
    data["write_gate"]["open"] = open_entries
    return PolicyEngine(data, yaml.safe_dump(data))


def test_empty_gate_is_valid():
    assert _engine([]).write_gate_open == []


def test_one_cache_pair_is_valid():
    assert _engine([CACHE_PAIR]).write_gate_open == [CACHE_PAIR]


def test_vm095_pair_is_refused():
    with pytest.raises(ValueError, match="write_gate.open must be empty"):
        _engine([{"capability": "container.start", "target": "vm-095/container:argus-lab-cache"}])


def test_non_lab_target_is_refused():
    with pytest.raises(ValueError, match="write_gate.open must be empty"):
        _engine([{"capability": "container.start", "target": "vm-166/container:database"}])


def test_unknown_capability_is_refused():
    with pytest.raises(ValueError, match="write_gate.open must be empty"):
        _engine([{"capability": "host.shell", "target": CACHE_PAIR["target"]}])


def test_extra_entry_keys_are_refused():
    with pytest.raises(ValueError, match="write_gate.open must be empty"):
        _engine([{**CACHE_PAIR, "route": "POST /containers/argus-lab-cache/start"}])


def test_duplicate_pairs_are_refused():
    with pytest.raises(ValueError, match="write_gate.open must be empty"):
        _engine([CACHE_PAIR, CACHE_PAIR])


def test_string_entry_is_refused():
    with pytest.raises(ValueError, match="write_gate.open must be empty"):
        _engine(["container.start"])
