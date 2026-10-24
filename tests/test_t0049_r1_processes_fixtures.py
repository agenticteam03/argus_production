"""R1: restart cases replay the Docker /top fixture through container.processes."""
from __future__ import annotations

from pathlib import Path

import pytest

from argus.capabilities.catalog import build_catalog
from argus.capabilities.spec import ExecutorError
from argus.domain.model import TargetRef
from argus.evaluation.cases import load_cases
from argus.evaluation.replay import FixtureExecutor

CASES = Path(__file__).resolve().parent / "eval" / "cases"
RESTART_CASES = (
    "restart-crash-01",
    "restart-crash-02",
    "restart-exit0-job-01",
    "restart-oom-01",
    "restart-oom-02",
    "restart-sigkill-01",
)
PROCESS_SPEC = next(spec for spec in build_catalog() if spec.name == "container.processes")


@pytest.mark.parametrize("case_id", RESTART_CASES)
def test_process_read_replays_each_restart_case_top_fixture(case_id):
    case = next(item for item in load_cases(CASES) if item.id == case_id)
    target = TargetRef.parse(case.target)
    path = f"/containers/{target.name}/top"
    fixture = case.fixtures["docker_read"].get(path)
    executor = FixtureExecutor(case.fixtures["docker_read"])

    try:
        result = PROCESS_SPEC.impl(PROCESS_SPEC.args_model(), target, None, executor)
    except ExecutorError as error:
        pytest.fail(f"{case_id}: container.processes replay failed for {path}: {error}")

    assert fixture is not None, f"{case_id}: missing {path} fixture"
    assert {key: value for key, value in result.values.items() if key != "collected_at"} == {
        key: value for key, value in fixture.items() if key != "collected_at"
    }

    status = case.fixtures["docker_read"][f"/containers/{target.name}/status"]
    host_processes = case.fixtures["host_probe"]["/processes"]["processes"]
    matching_host_processes = [
        {"pid": process["pid"], "command": process["command"]}
        for process in host_processes
        if process.get("container_id") == status["id"]
    ]
    assert [
        {"pid": process["pid"], "command": process["command"]}
        for process in fixture["processes"]
    ] == matching_host_processes, f"{case_id}: /top must match the live host process snapshot"
