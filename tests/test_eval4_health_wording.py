"""EVAL-4: a health-check diagnosis may name the failing check in other words; stored results are re-graded offline.

EVAL-3 step 2 (55 cases x 5): `health_check_failed` 0.72 strict. 6 of its 8 misses named the right root cause and
the right class but wrote "health probe", "unhealthy" or "failed health probes" instead of the label's literal
"health check" (the core accuracy, which leaves the words out, was already 0.99). The five `health-*` cases now accept
`health check`, `healthcheck`, `health probe` and `unhealthy`. Relabelled after seeing the answers (disclosed in the
task, the journal and the PR); fixtures, outcomes and root causes unchanged. `argus.evaluation.regrade` grades a stored
results file again with the current labels, without a model call.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from argus.evaluation.cases import load_cases
from argus.evaluation.regrade import main, runs_from_file
from argus.evaluation.replay import CaseRun
from argus.evaluation.score import grade

CASES = Path(__file__).resolve().parent / "eval" / "cases"
HEALTH = ["health-api-vm095-01", "health-api-vm095-02", "health-api-vm166-01", "health-api-vm166-02", "health-db-vm166-01"]
WORDS = ["health check", "healthcheck", "health probe", "unhealthy"]

# Diagnoses the model wrote in EVAL-3 step 2 (eval-20261012-182757.jsonl), each with the right outcome and root cause.
SEEN = {
    "health-api-vm095-01": "The container is running but intentionally serving HTTP 503 because maintenance mode is "
                           "enabled by the flag file `/srv/maintenance`; Docker consequently records three failed health "
                           "probes.",
    "health-api-vm095-02": "The container is running but unhealthy because its HTTP process cannot bind to 0.0.0.0:8080: "
                           "the port is already in use.",
    "health-api-vm166-01": "Root cause is an application configuration failure in argus-lab-api: its settings loader "
                           "raises KeyError: 'FEATURE_FLAGS', causing /health to return HTTP 500 and Docker to mark the "
                           "running container unhealthy.",
    "health-api-vm166-02": "The API container itself is the supported root cause of the unhealthy state: its health "
                           "probe timed out after 3 seconds while its worker pool was exhausted (8/8 threads busy).",
}


def _cases():
    return {c.id: c for c in load_cases(CASES)}


def _run(case, diagnosis):
    return CaseRun(case_id=case.id, outcome="diagnosed", incident_class=case.label.incident_class,
                   root_cause_target=case.label.root_cause, diagnosis=diagnosis, findings=[], model_calls=2,
                   reads=[], passages=[], audit_events=[])


def test_the_health_cases_accept_the_failing_check_in_other_words():
    for cid in HEALTH:
        label = yaml.safe_load((CASES / f"{cid}.yaml").read_text(encoding="utf-8"))["label"]
        assert label["diagnosis_any"] == WORDS, cid
        assert label["outcome"] == "diagnosed" and label["class"] == "health_check_failed"     # the rest unchanged


def test_the_answers_seen_in_eval3_now_pass_and_a_silent_one_still_fails():
    cases = _cases()
    for cid, text in SEEN.items():
        assert grade(cases[cid], _run(cases[cid], text)) == [], cid
    silent = _run(cases["health-api-vm166-01"], "The API returns HTTP 500 because of a missing configuration key.")
    assert any("does not mention" in p for p in grade(cases["health-api-vm166-01"], silent))


def test_the_abstain_case_is_unchanged():
    label = yaml.safe_load((CASES / "ambiguous-health-no-cause.yaml").read_text(encoding="utf-8"))["label"]
    assert label["outcome"] == "no_action_escalated" and label["abstain"] is True and "diagnosis_any" not in label


def test_regrade_grades_a_stored_results_file_without_a_model(tmp_path, capsys):
    cases = _cases()
    c = cases["health-api-vm166-02"]
    rows = [{"case": c.id, "trial": 1, "outcome": "diagnosed", "incident_class": "health_check_failed",
             "root_cause_target": c.label.root_cause, "diagnosis": SEEN[c.id], "findings": [], "model_calls": 2,
             "reads": [["container.health", c.target, "ok"]], "passages": [["RB-002", "x"]], "audit_events": []},
            {"case": c.id, "trial": 2, "outcome": "no_action_escalated", "incident_class": "health_check_failed",
             "root_cause_target": None, "diagnosis": "", "findings": [], "model_calls": 2, "reads": [], "passages": [],
             "audit_events": []}]
    f = tmp_path / "eval.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    runs = runs_from_file(f, list(cases.values()))
    assert [grade(case, run) == [] for case, run in runs] == [True, False]
    assert main([str(f)]) == 0
    out = capsys.readouterr().out
    assert "cases 2  passed 1" in out and "health_check_failed" in out
