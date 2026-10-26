"""Regrading preserves additive ranking inputs when result rows contain them."""
from __future__ import annotations

import json

from argus.evaluation.cases import Case
from argus.evaluation.regrade import runs_from_file


def test_regrade_reads_recorded_hypothesis_and_evidence_inputs(tmp_path):
    case = Case.model_validate({
        "id": "case-1", "category": "class", "target": "api", "request": "report", "reason": "api errors",
        "label": {"outcome": "diagnosed", "class": "dependency_unavailable", "root_cause": "backend"},
    })
    hypotheses = [{"id": "h1", "target": "backend", "cause_class": "dependency_unavailable",
                   "status": "supported", "rank": 1, "chosen": True,
                   "support": ["obs-backend"], "against": []}]
    evidence = [{"evidence_id": "obs-backend", "kind": "observation", "target": "backend"}]
    path = tmp_path / "results.jsonl"
    path.write_text(json.dumps({"case": case.id, "hypotheses": hypotheses, "evidence": evidence}) + "\n",
                    encoding="utf-8")

    _, run = runs_from_file(path, [case])[0]

    assert run.hypotheses == hypotheses
    assert run.evidence == evidence


def test_regrade_reads_old_rows_without_the_new_fields(tmp_path):
    case = Case.model_validate({
        "id": "case-1", "category": "class", "target": "api", "request": "report", "reason": "api errors",
        "label": {"outcome": "diagnosed", "class": "dependency_unavailable", "root_cause": "backend"},
    })
    path = tmp_path / "results.jsonl"
    path.write_text(json.dumps({"case": case.id, "outcome": "diagnosed"}) + "\n", encoding="utf-8")

    _, run = runs_from_file(path, [case])[0]

    assert run.hypotheses == [] and run.evidence == []
