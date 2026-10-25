"""TASK-19 fixture structure; the D-003 replay test checks baseline agreement with the labels."""
from __future__ import annotations

import pytest
import yaml

from argus.evaluation.replay import FixtureExecutor
from test_core import ROOT

CASES = ROOT / "tests" / "eval" / "cases"
NEW_CASE_IDS = {
    "dep-cache-oom-killed",
    "dep-db-stopped",
    "dep-db-wrong-network",
    "ambiguous-dep-dns-vantage",
    "ambiguous-dep-auth-failure",
    "ambiguous-dep-intermittent-timeout",
}
DEPENDENCY_NAMES = {
    "dep-cache-oom-killed": "argus-lab-cache",
    "dep-db-stopped": "argus-lab-db",
    "dep-db-wrong-network": "argus-lab-db",
    "ambiguous-dep-dns-vantage": "argus-lab-backend",
    "ambiguous-dep-auth-failure": "argus-lab-cache",
    "ambiguous-dep-intermittent-timeout": "argus-lab-backend",
}


@pytest.fixture()
def ev(monkeypatch):
    monkeypatch.setenv("ARGUS_JWT_KEY", "x" * 40)
    from argus import evaluation
    return evaluation


def test_new_dependency_cases_cover_valid_diagnoses_and_abstentions(ev):
    cases = {case.id: case for case in ev.load_cases(CASES) if case.id in NEW_CASE_IDS}
    assert set(cases) == NEW_CASE_IDS
    assert sum(case.category == "class" for case in cases.values()) == 3
    assert sum(case.category == "ambiguous" for case in cases.values()) == 3

    inventory = yaml.safe_load((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    refs = {target["ref"] for target in inventory["targets"]}
    for case in cases.values():
        assert case.label.incident_class == "dependency_unavailable", case.id
        assert case.target in refs, case.id
        assert "*" in case.fixtures.get("network_probe", {}), case.id
        docker = case.fixtures.get("docker_read", {})
        dependency = case.label.expected_hypotheses
        if case.category == "class":
            assert case.label.outcome == "diagnosed", case.id
            assert case.label.root_cause in refs, case.id
            assert "RB-003" in case.label.runbooks, case.id
            assert dependency is not None, case.id
            assert case.label.root_cause in dependency.supported, case.id
            assert case.target in dependency.ruled_out, case.id
        else:
            assert case.label.outcome == "no_action_escalated", case.id
            assert case.label.abstain, case.id

        target_name = case.target.split("container:", 1)[1]
        dependency_name = DEPENDENCY_NAMES[case.id]
        docker_executor = FixtureExecutor(docker)
        for suffix in ("stats", "health", "events"):
            for name in (target_name, dependency_name):
                path = f"/containers/{name}/{suffix}"
                assert path in docker, (case.id, path)
                assert docker_executor.get(path), (case.id, path)

    oom = cases["dep-cache-oom-killed"]
    cache = "vm-166/container:argus-lab-cache"
    cache_status = oom.fixtures["docker_read"]["/containers/argus-lab-cache/status"]
    cache_events = oom.fixtures["docker_read"]["/containers/argus-lab-cache/events"]["events"]
    assert "memory_exhaustion" in oom.label.expected_hypotheses.supported
    assert cache_status["state"] == "exited" and cache_status["oom_killed"] is True
    assert cache_status["exit_code"] == 137
    assert {event["action"] for event in cache_events} == {"oom", "die"}
    assert "memory_exhaustion" in oom.label.expected_hypotheses.supported
    assert "cache" in oom.label.diagnosis_any

    for case_id in ("dep-cache-oom-killed", "dep-db-stopped"):
        target = cases[case_id].target.split("container:", 1)[1]
        dependency_name = DEPENDENCY_NAMES[case_id]
        docker = cases[case_id].fixtures["docker_read"]
        assert docker[f"/containers/{target}/status"]["state"] == "running", case_id
        assert docker[f"/containers/{dependency_name}/status"]["state"] == "exited", case_id

    for case_id, dependency_ref in (("dep-cache-oom-killed", cache),
                                    ("dep-db-stopped", "vm-166/container:argus-lab-db")):
        name = dependency_ref.split("container:", 1)[1]
        probes = cases[case_id].fixtures["network_probe"]
        assert probes[f"/dns?name={name}"]["ok"] is False, case_id
        assert probes["*"]["ok"] is False, case_id

    isolated = cases["dep-db-wrong-network"].fixtures["docker_read"]
    leaker_networks = set(isolated["/containers/argus-lab-leaker/status"]["networks"])
    db_networks = set(isolated["/containers/argus-lab-db/status"]["networks"])
    assert isolated["/containers/argus-lab-db/status"]["state"] == "running"
    assert not leaker_networks & db_networks
    wrong_network_probes = cases["dep-db-wrong-network"].fixtures["network_probe"]
    assert wrong_network_probes["/dns?name=argus-lab-db"]["ok"] is False
    assert wrong_network_probes["/tcp?host=argus-lab-db&port=5432"]["error"] == "Name does not resolve"
    assert wrong_network_probes["*"]["ok"] is False
