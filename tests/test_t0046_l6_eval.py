"""T-0046 L6: replay five incident variants where recorded link evidence changes the diagnosis."""
from pathlib import Path

from argus.detectors.classes import CLASSES
from argus.evaluation.cases import load_cases
from argus.evaluation.replay import run_case
from argus.evaluation.score import grade

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "t0046-sc03-live-cache-link", "t0046-sc07-live-backend-link", "t0046-health-dependency-link",
    "t0046-sc08-upstream-link-broken", "t0046-sc08-upstream-link-slow",
}


def test_five_scenario_variants_use_link_history_and_preserve_the_expected_cause(tmp_path):
    cases = [case for case in load_cases(ROOT / "tests" / "eval" / "cases") if case.id in EXPECTED]
    assert {case.id for case in cases} == EXPECTED

    for case in cases:
        result = run_case(case, tmp_path, strategy="baseline")
        assert result.outcome == case.label.outcome, (case.id, result.diagnosis, result.reads)
        assert result.incident_class == case.label.incident_class, (case.id, result.diagnosis)
        assert result.root_cause_target == case.label.root_cause, (case.id, result.diagnosis)
        assert any(name == "network.link_states" and status == "ok" for name, _, status in result.reads), case.id
        assert grade(case, result) == [], (case.id, result.diagnosis)


def test_without_the_link_states_offer_every_one_of_the_five_cases_fails(tmp_path, monkeypatch):
    """The control arm: the same cases with `network.link_states` offered to no class. SC-03, SC-07 and the health case
    name another root cause; the SC-08 cases keep the upstream as the cause but give the wrong mechanism (a slow or
    saturated upstream for a broken link) or no recorded evidence for the slow one."""
    for spec in CLASSES:
        monkeypatch.setattr(spec, "tool_tags", set(spec.tool_tags) - {"link_states"})
    cases = [case for case in load_cases(ROOT / "tests" / "eval" / "cases") if case.id in EXPECTED]

    for case in cases:
        result = run_case(case, tmp_path, strategy="baseline")
        assert not any(name == "network.link_states" for name, _, _ in result.reads), case.id
        assert grade(case, result), (case.id, result.diagnosis)
