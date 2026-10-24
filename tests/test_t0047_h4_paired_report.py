"""Offline comparison of paired H4 evaluation result files."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from argus.evaluation.compare import compare_files, hypothesis_problem_kind


def _cases(folder: Path) -> Path:
    folder.mkdir()
    cases = [
        ("dep-1", "dependency_unavailable", "vm-166/container:api"),
        ("restart-1", "container_restart_loop", "vm-166/container:worker"),
    ]
    for case_id, expected_class, target in cases:
        (folder / f"{case_id}.yaml").write_text(yaml.safe_dump({
            "id": case_id,
            "category": "class",
            "target": target,
            "request": "report",
            "reason": "synthetic paired report case",
            "label": {"outcome": "diagnosed", "class": expected_class, "root_cause": target},
        }), encoding="utf-8")
    return folder


def _row(case_id: str, trial: int, *, predicted_class: str, target: str, duration: int,
         tokens: bool = True, problems: list[str] | None = None, hard: dict | None = None) -> dict:
    row = {
        "case": case_id,
        "category": "class",
        "strategy": "model_loop",
        "model": "configured",
        "verdict": "PASS",
        "problems": [],
        "hard": hard or {"actions_outside_policy": 0, "secrets_in_model_requests": 0,
                          "forbidden_target_reads": 0, "unsupported_root_cause": 0},
        "outcome": "diagnosed",
        "incident_class": predicted_class,
        "root_cause_target": target,
        "diagnosis": "the target is diagnosed",
        "findings": [],
        "model_calls": 1,
        "reads": [],
        "passages": [],
        "audit_events": [],
        "invalid_decisions": [],
        "duration_ms": duration,
        "trial": trial,
        "hypotheses": [],
        "ranking_disagrees": False,
        "hypothesis_problems": problems or [],
        "observed": [target],
    }
    if tokens:
        row["input_tokens"] = 11
        row["output_tokens"] = 7
    return row


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_report_pairs_rows_scores_by_expected_class_and_keeps_missing_tokens_unknown(tmp_path):
    cases = _cases(tmp_path / "cases")
    dependency = _row("dep-1", 1, predicted_class="container_restart_loop",
                      target="vm-166/container:api", duration=100,
                      problems=["step 2 conclude: h1: ruled out without evidence against it", "new check added"])
    dependency.pop("input_tokens")
    before = _write(tmp_path / "before.jsonl", [
        dependency,
        _row("restart-1", 1, predicted_class="container_restart_loop", target="vm-166/container:worker", duration=300,
             hard={"actions_outside_policy": 0, "secrets_in_model_requests": 0,
                   "forbidden_target_reads": 0, "unsupported_root_cause": 2}),
    ])
    after = _write(tmp_path / "after.jsonl", [
        _row("dep-1", 1, predicted_class="dependency_unavailable", target="vm-166/container:api", duration=200),
        _row("restart-1", 1, predicted_class="container_restart_loop", target="vm-166/container:worker", duration=400),
    ])

    report = compare_files(before, after, cases)

    assert report["before"]["per_class"] == {
        "container_restart_loop": {"runs": 1, "correct": 1, "accuracy": 1.0},
        "dependency_unavailable": {"runs": 1, "correct": 0, "accuracy": 0.0},
    }
    assert report["before"]["hard_failures"]["unsupported_root_cause"] == 2
    assert report["before"]["hypothesis_problems"]["ruled_out_without_against"] == 1
    assert report["before"]["hypothesis_problems"]["unclassified"] == 1
    assert report["before"]["unclassified_messages"] == {"new check added": 1}
    assert report["before"]["model_calls"] == 2
    assert report["before"]["input_tokens"] is None
    assert report["before"]["output_tokens"] == 14
    assert report["before"]["token_rows_missing"] == {"input_tokens": 1, "output_tokens": 0}
    assert report["before"]["latency_ms_p50"] == 300
    assert report["after"]["input_tokens"] == 22
    assert report["after"]["hypothesis_problems"]["unclassified"] == 0


def test_mismatched_coverage_is_reported_clearly(tmp_path):
    cases = _cases(tmp_path / "cases")
    before = _write(tmp_path / "before.jsonl", [
        _row("dep-1", 1, predicted_class="dependency_unavailable", target="vm-166/container:api", duration=10),
    ])
    after = _write(tmp_path / "after.jsonl", [
        _row("restart-1", 1, predicted_class="container_restart_loop", target="vm-166/container:worker", duration=10),
    ])

    with pytest.raises(ValueError, match="coverage mismatch"):
        compare_files(before, after, cases)


@pytest.mark.parametrize("mutate, message", [
    (lambda rows: rows + [dict(rows[0])], "duplicate case/trial"),
    (lambda rows: [{**rows[0], "duration_ms": -1}, rows[1]], "duration_ms"),
    (lambda rows: [{**rows[0], "trial": True}, rows[1]], "trial"),
])
def test_bad_rows_fail_with_actionable_errors(tmp_path, mutate, message):
    cases = _cases(tmp_path / "cases")
    rows = [
        _row("dep-1", 1, predicted_class="dependency_unavailable", target="vm-166/container:api", duration=10),
        _row("restart-1", 1, predicted_class="container_restart_loop", target="vm-166/container:worker", duration=20),
    ]
    before = _write(tmp_path / "before.jsonl", mutate(rows))
    after = _write(tmp_path / "after.jsonl", rows)

    with pytest.raises(ValueError, match=message):
        compare_files(before, after, cases)


@pytest.mark.parametrize("field", ["model", "strategy"])
def test_model_and_strategy_must_match_between_arms(tmp_path, field):
    cases = _cases(tmp_path / "cases")
    rows = [
        _row("dep-1", 1, predicted_class="dependency_unavailable", target="vm-166/container:api", duration=10),
        _row("restart-1", 1, predicted_class="container_restart_loop", target="vm-166/container:worker", duration=20),
    ]
    before = _write(tmp_path / "before.jsonl", rows)
    replacement = "none" if field == "model" else "baseline"
    after = _write(tmp_path / "after.jsonl", [{**r, field: replacement} for r in rows])

    with pytest.raises(ValueError, match="metadata mismatch"):
        compare_files(before, after, cases)


def test_cli_emits_a_machine_readable_report(tmp_path, capsys):
    from argus.evaluation.compare import main

    cases = _cases(tmp_path / "cases")
    rows = [
        _row("dep-1", 1, predicted_class="dependency_unavailable", target="vm-166/container:api", duration=10),
        _row("restart-1", 1, predicted_class="container_restart_loop", target="vm-166/container:worker", duration=20),
    ]
    before = _write(tmp_path / "before.jsonl", rows)
    after = _write(tmp_path / "after.jsonl", rows)

    assert main(["--before", str(before), "--after", str(after), "--cases", str(cases)]) == 0
    assert json.loads(capsys.readouterr().out)["metadata"] == {"model": "configured", "strategy": "model_loop"}


@pytest.mark.parametrize("message, expected", [
    ("hypotheses must be a list", "invalid_hypotheses_value"),
    ("6 hypotheses: at most 5", "too_many_hypotheses"),
    ("a hypothesis fails its schema: id missing", "schema_invalid"),
    ("h1: the same id twice", "duplicate_id"),
    ("h1: cites evidence not stored for this incident", "unknown_evidence"),
    ("h1: the same evidence both for and against it", "conflicting_evidence"),
    ("h1: no target, but its relation is dependency, not external", "invalid_target_relation"),
    ("h1: target x is not in the incident's scope", "target_out_of_scope"),
    ("h1: an external cause supported without an observation of a target in scope", "external_without_observation"),
    ("h1: supported without an observation of its own target", "supported_without_observation"),
    ("h1: ruled out without evidence against it", "ruled_out_without_against"),
    ("a conclusion without hypotheses", "conclusion_without_hypotheses"),
    ("a root_cause_target without a chosen hypothesis", "root_cause_without_chosen"),
    ("chosen 'h8' is not one of the hypotheses", "chosen_id_unknown"),
    ("chosen h1 is external: an external cause is never chosen", "chosen_external"),
    ("chosen h1 is untested, not supported", "chosen_not_supported"),
    ("chosen h1 has target x, not the root_cause_target y", "chosen_target_mismatch"),
])
def test_h1_problem_phrases_have_deterministic_buckets(message, expected):
    assert hypothesis_problem_kind(message) == expected


def test_malformed_json_is_reported_with_file_and_line(tmp_path):
    cases = _cases(tmp_path / "cases")
    before = tmp_path / "before.jsonl"
    before.write_text("{bad json}\n", encoding="utf-8")
    after = _write(tmp_path / "after.jsonl", [
        _row("dep-1", 1, predicted_class="dependency_unavailable", target="vm-166/container:api", duration=10),
        _row("restart-1", 1, predicted_class="container_restart_loop", target="vm-166/container:worker", duration=20),
    ])

    with pytest.raises(ValueError, match=r"before.jsonl:1: invalid JSON"):
        compare_files(before, after, cases)
