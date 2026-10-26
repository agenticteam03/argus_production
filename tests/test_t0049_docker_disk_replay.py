from datetime import datetime
from pathlib import Path

import pytest

from argus.capabilities.catalog import build_catalog
from argus.domain.model import TargetRef
from argus.evaluation.cases import load_cases
from argus.evaluation.replay import FixtureExecutor

CASE_DIR = Path(__file__).parent / "eval" / "cases"
DISK_CASE_IDS = tuple(sorted(path.stem for path in CASE_DIR.glob("disk-*.yaml")))
STOPPED_CASE_IDS = {"disk-filler-stopped", "disk-filler-stopped-with-history"}
HOST = TargetRef.parse("vm-166/host:vm-166")
EXPECTED_FIELDS = {"images", "containers", "volumes", "build_cache_bytes", "collected_at"}


def test_every_disk_case_is_found():
    assert len(DISK_CASE_IDS) >= 8 and STOPPED_CASE_IDS <= set(DISK_CASE_IDS)


def test_each_disk_case_replays_docker_disk_usage_in_executor_shape():
    cases = {case.id: case for case in load_cases(CASE_DIR)}
    disk_spec = {spec.name: spec for spec in build_catalog()}["docker.disk_usage"]

    for case_id in DISK_CASE_IDS:
        case = cases[case_id]
        executor = FixtureExecutor(case.fixtures.get("docker_read", {}))
        try:
            result = disk_spec.impl(disk_spec.args_model(), HOST, None, executor)
        except Exception as exc:
            pytest.fail(f"{case_id}: docker.disk_usage replay failed: {exc}")

        data = result.values
        assert set(data) == EXPECTED_FIELDS, case_id
        for group, fields in (
            ("images", ("count", "bytes", "unused_count", "unused_bytes")),
            ("containers", ("count", "writable_bytes", "stopped_count")),
            ("volumes", ("count", "bytes", "unused_count", "unused_bytes")),
        ):
            assert set(data[group]) == set(fields), case_id
            assert all(type(data[group][field]) is int and data[group][field] >= 0 for field in fields), case_id
        assert data["containers"]["stopped_count"] == int(case_id in STOPPED_CASE_IDS), case_id
        assert type(data["build_cache_bytes"]) is int and data["build_cache_bytes"] >= 0, case_id
        assert isinstance(data["collected_at"], str) and data["collected_at"], case_id
        datetime.fromisoformat(data["collected_at"])
