"""T-0047 H4 sensitivity analysis for recorded hypothesis rankings."""
from __future__ import annotations

import json
from io import StringIO

from argus.application.ranking import Weights
from argus.evaluation.cases import Case
from argus.evaluation import weights_sensitivity
from argus.evaluation.weights_sensitivity import analyze_rows, render_report, weight_sets


def _case() -> Case:
    return Case.model_validate({
        "id": "case-1", "category": "class", "target": "api", "request": "report", "reason": "api errors",
        "label": {"outcome": "diagnosed", "class": "dependency_unavailable", "root_cause": "backend",
                  "expected_hypotheses": {"supported": ["backend"], "ruled_out": ["api"]}},
    })


def _row(*, include_evidence: bool = True) -> dict:
    row = {
        "case": "case-1", "chosen": "h1",
        "hypotheses": [
            {"id": "h1", "target": "backend", "cause_class": "dependency_unavailable", "status": "supported",
             "support": ["obs-backend"], "against": [], "chosen": True},
            {"id": "h2", "target": "database", "cause_class": "database_failure", "status": "supported",
             "support": ["metric-backend"], "against": [], "chosen": False},
            {"id": "h3", "target": "api", "cause_class": "other", "status": "ruled_out",
             "support": [], "against": ["obs-backend"], "chosen": False},
        ],
    }
    if include_evidence:
        row["evidence"] = [
            {"evidence_id": "obs-backend", "kind": "observation", "target": "backend"},
            {"evidence_id": "metric-backend", "kind": "metric_snapshot", "target": "database"},
        ]
    return row


def test_weight_sets_vary_one_score_weight_at_a_time_and_the_untested_penalty():
    variants = weight_sets(Weights())
    assert len(variants) == 15
    assert variants["current"] == Weights()
    fields = ("own_observation", "own_metric_snapshot", "other_observation", "alert", "peer_finding",
              "reported_symptom")
    for field in fields:
        assert getattr(variants[f"{field}_half"], field) == getattr(Weights(), field) / 2
        assert getattr(variants[f"{field}_double"], field) == getattr(Weights(), field) * 2
        for other in fields:
            if other != field:
                assert getattr(variants[f"{field}_half"], other) == getattr(Weights(), other)
                assert getattr(variants[f"{field}_double"], other) == getattr(Weights(), other)
        assert variants[f"{field}_half"].max_target_records == Weights().max_target_records
        assert variants[f"{field}_double"].max_target_records == Weights().max_target_records
    assert variants["untested_penalty_0"].untested_penalty == 0
    assert variants["untested_penalty_1"].untested_penalty == 1
    assert variants["own_observation_half"].own_metric_snapshot == 2.0


def test_each_weight_set_reranks_from_recorded_evidence_and_reports_class_metrics():
    summary = analyze_rows([_row()], {"case-1": _case()}, Weights())
    assert summary["scorable"] == 1 and summary["not_scorable"] == 0
    assert summary["sets"]["current"]["top1"] == {"correct": 1, "total": 1, "accuracy": 1.0}
    half = summary["sets"]["own_observation_half"]
    assert half["top1"] == {"correct": 0, "total": 1, "accuracy": 0.0}
    assert half["top3"] == {"correct": 1, "total": 1, "accuracy": 1.0}
    assert half["ruled_out_recall"] == {"found": 1, "expected": 1, "recall": 1.0}
    assert half["ranking_disagrees"] == {"count": 1, "total": 1}
    assert half["per_class"]["dependency_unavailable"]["top1"]["accuracy"] == 0.0
    assert "ruled-out 1/1 (1.000)" in render_report("fixture.jsonl", summary)


def test_rows_without_evidence_are_reported_not_scorable():
    summary = analyze_rows([_row(include_evidence=False)], {"case-1": _case()}, Weights())
    assert summary["scorable"] == 0 and summary["not_scorable"] == 1
    assert summary["not_scorable_reasons"] == {"missing evidence records": 1}
    assert summary["sets"]["current"]["top1"] == {"correct": 0, "total": 0, "accuracy": None}
    assert summary["not_scorable_by_class"] == {"dependency_unavailable": 1}
    assert summary["sets"]["current"]["per_class"]["dependency_unavailable"]["rows"] == 1


def test_legacy_hypothesis_rows_missing_support_ids_are_not_scorable():
    row = _row()
    row.pop("evidence")
    row["hypotheses"][0].pop("support")
    row["hypotheses"][0].pop("against")
    summary = analyze_rows([row], {"case-1": _case()}, Weights())
    assert summary["scorable"] == 0 and summary["not_scorable"] == 1
    assert summary["not_scorable_reasons"] == {"hypotheses[0] missing support,against": 1}


def test_cli_reads_vm_rows_from_stdin_and_displays_the_given_filename(monkeypatch, capsys):
    monkeypatch.setattr(weights_sensitivity, "load_cases", lambda _path: [_case()])
    monkeypatch.setattr(weights_sensitivity, "load_ranking", lambda _path: Weights())
    monkeypatch.setattr(weights_sensitivity.sys, "stdin", StringIO(json.dumps(_row(include_evidence=False)) + "\n"))
    assert weights_sensitivity.main(["--cases", "unused", "--stdin-name", "h5b-before.jsonl", "-"]) == 0
    output = capsys.readouterr().out
    assert "result file: h5b-before.jsonl" in output
    assert "not scorable 1" in output
    assert "missing evidence records: 1" in output
