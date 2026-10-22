"""OP-013: a held-out evaluation set for the two classes D-003 put under the baseline (`dependency_unavailable`,
`nginx_upstream_failure`). The baseline's rules were written from `tests/eval/cases`, so its 1.00 there is an upper
bound; these cases were written without reading or changing those rules. They live in their own folder so that CI's
offline evaluation and the D-003 test never load them: a held-out case that a rule fix is tuned against stops being
held out. These tests check the set's structure only, never which strategy passes it.
"""
from __future__ import annotations

import pytest
import yaml

from test_core import ROOT

CASES = ROOT / "tests" / "eval" / "cases"
HELDOUT = ROOT / "tests" / "eval" / "heldout" / "cases"
CLASSES = ("dependency_unavailable", "nginx_upstream_failure")


@pytest.fixture()
def ev(monkeypatch):
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    from argus import evaluation
    return evaluation


def test_the_held_out_set_has_at_least_5_cases_per_class_and_one_to_escalate(ev):
    cases = ev.load_cases(HELDOUT)
    for cls in CLASSES:
        mine = [c for c in cases if c.label.incident_class == cls]
        assert len(mine) >= 5, f"{cls}: {len(mine)} held-out cases"
        assert any(c.label.abstain for c in mine), f"{cls}: no held-out case where the right answer is to escalate"
    assert {c.label.incident_class for c in cases} <= set(CLASSES)


def test_the_held_out_ids_are_marked_and_never_in_the_main_set(ev):
    held = {c.id for c in ev.load_cases(HELDOUT)}
    assert all(i.startswith("heldout-") for i in held)
    assert held.isdisjoint({c.id for c in ev.load_cases(CASES)})
    assert not list(CASES.glob("heldout-*")), "a held-out case in tests/eval/cases is loaded by CI and the D-003 test"


def test_every_held_out_target_is_a_lab_container_of_the_inventory(ev):
    inv = yaml.safe_load((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    refs = {t["ref"] for t in inv["targets"]}
    for c in ev.load_cases(HELDOUT):
        assert c.target in refs and "/container:argus-lab-" in c.target, c.id
        if c.label.root_cause:
            assert c.label.root_cause in refs, c.id


def test_every_held_out_case_has_a_default_network_answer(ev):
    """As the main set (test_evaluation.py): a healthy network answers; a case says only where it fails."""
    for c in ev.load_cases(HELDOUT):
        assert "*" in c.fixtures.get("network_probe", {}), c.id
