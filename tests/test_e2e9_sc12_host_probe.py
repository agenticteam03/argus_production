"""E2E-9: SC-12 accepts a diagnosis made without the stopped read gateway (E2E-8 step 2, SC-12 run 1).

With vm-166's read gateway stopped, the model may still read the host probe (another executor) and diagnose the OOM
loop from the kernel's OOM records, as in `inc_abe543607681`. "Never `diagnosed`" was older than the host probe; what
SC-12 must hold is "no diagnosis without evidence": `if_diagnosed` passes a `diagnosed` only with the right root
cause, no successful read through the stopped executor, and at least one successful read through another.
"""
from __future__ import annotations

import pytest

from test_e2e_runner import CATALOGUE, e2e, incident

WORKER = "vm-166/container:argus-lab-worker"
HOST = "vm-166/host:vm-166"
EXP = {"outcome": ["no_action_escalated", "undiagnosable", "diagnosed"], "class": "container_restart_loop",
       "reads_on": "vm-166", "if_diagnosed": {"root_cause": WORKER, "executor_down": "docker_read"}}


def read(executor: str, status: str, target: str = WORKER, capability: str = "container.status") -> dict:
    return {"target": target, "caller": "model", "capability": capability, "executor": executor, "status": status}


# the reads of SC-12 run 1 (`inc_abe543607681`)
RUN1 = [read("docker_read", "error"), read("prometheus", "ok", capability="metrics.memory_history"),
        read("host_probe", "ok", HOST, "host.memory"), read("host_probe", "ok", HOST, "host.kernel_oom_records")]


def test_a_diagnosis_from_the_host_probe_with_the_gateway_down_passes():
    assert e2e.grade(EXP, incident(evidence=RUN1)) == []


def test_an_escalation_still_passes_and_if_diagnosed_does_not_apply():
    inc = incident(outcome="no_action_escalated", root_cause_target=None, evidence=RUN1[:2])
    assert e2e.grade(EXP, inc) == []


def test_a_diagnosis_with_a_successful_read_through_the_stopped_executor_fails():
    """The gateway answered: the scenario did not cut it, so the run proves nothing."""
    problems = e2e.grade(EXP, incident(evidence=[*RUN1, read("docker_read", "ok", capability="container.logs")]))
    assert any("docker_read" in p for p in problems)


def test_a_diagnosis_without_any_successful_read_fails():
    problems = e2e.grade(EXP, incident(evidence=[read("docker_read", "error"), read("host_probe", "error", HOST)]))
    assert any("no successful read" in p for p in problems)


def test_a_diagnosis_of_the_wrong_root_cause_fails():
    problems = e2e.grade(EXP, incident(evidence=RUN1, root_cause_target=HOST))
    assert any("root cause" in p for p in problems)


@pytest.mark.parametrize("bad", [{"root_cause": WORKER}, {"executor_down": "docker_read"},
                                 {"root_cause": WORKER, "executor_down": "docker_read", "other": 1}, "docker_read"])
def test_if_diagnosed_needs_exactly_its_two_keys(bad):
    with pytest.raises(ValueError):
        e2e._investigation("SC-T", {"target": WORKER, "reason": "r", "kind": "report"},
                           {"outcome": "diagnosed", "if_diagnosed": bad})


def test_sc12_in_the_catalogue_allows_a_diagnosis_only_through_another_executor():
    cut, other = e2e.load_catalogue(CATALOGUE)["SC-12"].investigations
    assert set(cut[1]["outcome"]) == {"no_action_escalated", "undiagnosable", "diagnosed"}
    assert cut[1]["if_diagnosed"] == {"root_cause": WORKER, "executor_down": "docker_read"}
    assert cut[1]["reads_on"] == "vm-166" and other[1]["outcome"] == "no_incident"
