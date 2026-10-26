"""Offline checks for the T-0049 paired skills study harness."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "brain" / "tools"))
from skills_paired_eval import (
    SCHEMA_VERSION,
    SKILLS,
    TASKS,
    TASK_IDS_BY_SKILL,
    main,
    summarize,
    task_prompt_sha256,
    validate_study,
)


def _arm(condition: str, number: int, *, score: int = 3, safety_violation: bool = False,
         input_tokens: int | None = 100, output_tokens: int | None = 40, **changes) -> dict:
    return {
        "session_id": f"session-{condition}-{number}",
        "artifact_sha256": f"{number:064x}",
        "reviewer_blind": True,
        "score": score,
        "task_success": score >= 3,
        "safety_violation": safety_violation,
        "corrections": [],
        "failed_blocks": 0 if condition == "with_skill" else None,
        "trap_catches": [],
        "false_positives": [],
        "elapsed_seconds": 120 + number,
        "model_calls": 1,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        **changes,
    }


def _study() -> dict:
    pairs = []
    for number, task in enumerate(TASKS, start=1):
        pairs.append({
            "task_id": task["task_id"],
            "prompt_sha256": task_prompt_sha256(task["task_id"]),
            "run_order": ["without_skill", "with_skill"] if number % 2 else ["with_skill", "without_skill"],
            "arms": {
                "with_skill": _arm("with_skill", number, score=4 if number % 2 else 3,
                                    corrections=[{"severity": "minor", "note": "One wording change."}] if number % 2 == 0 else []),
                "without_skill": _arm("without_skill", number + 20, score=2,
                                      corrections=[{"severity": "major", "note": "One substantive correction."}],
                                      input_tokens=None if number % 3 == 1 else 100),
            },
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "study": {"model_id": "configured-model", "model_config_sha256": "a" * 64,
                  "repo_sha": "b" * 40, "policy_sha256": "c" * 64},
        "pairs": pairs,
        "activation_checks": [
            {"skill": skill, "relevant_selected": 3, "relevant_trials": 3,
             "irrelevant_selected": False, "irrelevant_prompt": "Summarize this generic paragraph.",
             "evidence": "blinded transcript record"}
            for skill in SKILLS
        ],
    }


def test_task_cards_cover_exactly_three_pairs_per_p0_p1_skill():
    assert len(TASKS) == 15
    assert set(TASK_IDS_BY_SKILL) == set(SKILLS)
    assert all(len(task_ids) == 3 for task_ids in TASK_IDS_BY_SKILL.values())
    assert len({task["task_id"] for task in TASKS}) == len(TASKS)
    assert all(task["prompt"] and task["acceptance_criteria"] and task["traps"] for task in TASKS)


def test_complete_canned_study_validates_and_summarizes_by_skill():
    study = _study()
    validate_study(study)

    report = summarize(study)

    assert report["tasks"] == 15
    assert report["condition_runs"] == 30
    assert report["decision"].startswith("descriptive only")
    assert set(report["skills"]) == set(SKILLS)
    assert all(item["pairs"] == 3 and item["wins"] == 3 for item in report["skills"].values())
    assert all(item["input_tokens_total"] is None for item in report["skills"].values())


def test_incomplete_pair_coverage_fails():
    study = _study()
    study["pairs"].pop()

    with pytest.raises(ValueError, match="missing task pairs"):
        validate_study(study)


@pytest.mark.parametrize("mutate, message", [
    (lambda study: study["pairs"].append(deepcopy(study["pairs"][0])), "duplicate pair"),
    (lambda study: study["pairs"][0]["arms"]["with_skill"].update(task_success=False), "task_success must match"),
    (lambda study: study["pairs"][0]["arms"]["with_skill"].update(
        corrections=[{"severity": "minor", "note": "Unexpected correction."}]), "score 4 requires no corrections"),
    (lambda study: study["pairs"][1]["arms"]["with_skill"]["corrections"].__setitem__(
        0, {"severity": "major", "note": "Major correction."}), "score 3 requires only minor corrections"),
    (lambda study: study["pairs"][0]["arms"]["with_skill"].update(
        score=0, task_success=False, safety_violation=True,
        corrections=[{"severity": "major", "note": "Missing critical marker."}]),
     "score 0 requires a critical correction record"),
    (lambda study: study["activation_checks"].pop(), "activation checks must cover all skills"),
    (lambda study: study["study"].update(repo_sha="G" * 40), "repo_sha must be a lowercase commit SHA"),
    (lambda study: study["pairs"][0]["arms"]["with_skill"].update(input_tokens=-1),
     "input_tokens must be null or an integer >= 0"),
    (lambda study: study["pairs"][0]["arms"]["with_skill"].update(output_tokens=-1),
     "output_tokens must be null or an integer >= 0"),
], ids=["duplicate-pair", "task-success", "score-4", "score-3", "score-0",
       "activation-coverage", "repo-sha", "input-tokens", "output-tokens"])
def test_each_validator_rule_rejects_its_invalid_record(mutate, message):
    study = _study()
    mutate(study)

    with pytest.raises(ValueError, match=message):
        validate_study(study)


def test_score_three_with_no_corrections_is_valid():
    study = _study()
    study["pairs"][1]["arms"]["with_skill"]["corrections"] = []

    validate_study(study)


def test_score_two_with_incomplete_task_and_no_recorded_corrections_is_valid():
    study = _study()
    arm = study["pairs"][0]["arms"]["without_skill"]
    arm["task_success"] = False
    arm["corrections"] = []

    validate_study(study)


def test_mismatched_prompt_or_reused_session_fails():
    study = _study()
    study["pairs"][0]["prompt_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="prompt hash"):
        validate_study(study)

    study = _study()
    study["pairs"][1]["arms"]["with_skill"]["session_id"] = study["pairs"][0]["arms"]["with_skill"]["session_id"]
    with pytest.raises(ValueError, match="duplicate session_id"):
        validate_study(study)


def test_unblind_assessment_and_inconsistent_safety_score_fail():
    study = _study()
    study["pairs"][0]["arms"]["with_skill"]["reviewer_blind"] = False
    with pytest.raises(ValueError, match="assessed blind"):
        validate_study(study)

    study = _study()
    arm = study["pairs"][0]["arms"]["with_skill"]
    arm["safety_violation"] = True
    with pytest.raises(ValueError, match="requires score 0"):
        validate_study(study)

    study = _study()
    arm = study["pairs"][0]["arms"]["with_skill"]
    arm["score"] = 0
    arm["task_success"] = False
    arm["corrections"] = [{"severity": "critical", "note": "Unsafe operation proposed."}]
    with pytest.raises(ValueError, match="score 0 requires a safety violation"):
        validate_study(study)


def test_malformed_schema_version_and_run_order_fail_cleanly():
    study = _study()
    study["schema_version"] = True
    with pytest.raises(ValueError, match="schema_version"):
        validate_study(study)

    study = _study()
    study["pairs"][0]["run_order"] = [{"not": "a condition"}, "without_skill"]
    with pytest.raises(ValueError, match="run_order"):
        validate_study(study)


def test_json_schema_and_cli_are_available_without_results(capsys):
    assert main(["--schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["title"] == "T-0049 skills paired evaluation results"
    assert schema["properties"]["pairs"]["type"] == "array"
    arm_schema = schema["properties"]["pairs"]["items"]["properties"]["arms"]["properties"]["with_skill"]
    assert set(arm_schema["required"]) == set(arm_schema["properties"])

    assert main(["--task-cards"]) == 0
    cards = json.loads(capsys.readouterr().out)
    assert len(cards["tasks"]) == 15
    assert "skill" not in cards["tasks"][0] and "title" not in cards["tasks"][0]
    assert "acceptance_criteria" not in cards["tasks"][0]

    assert main(["--review-criteria"]) == 0
    criteria = json.loads(capsys.readouterr().out)
    assert len(criteria["review_criteria"]) == 15
    assert "acceptance_criteria" in criteria["review_criteria"][0]

    assert main(["--rubric"]) == 0
    rubric = json.loads(capsys.readouterr().out)
    assert rubric["scores"]["0"].startswith("Any hard safety/policy violation")


def test_cli_reads_power_shell_utf8_json_and_emits_summary(tmp_path, capsys):
    results = tmp_path / "study.json"
    results.write_text(json.dumps(_study()), encoding="utf-8-sig")

    assert main(["--results", str(results)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["condition_runs"] == 30
    assert report["skills"]["code-bash-step"]["model_calls"] == 6
