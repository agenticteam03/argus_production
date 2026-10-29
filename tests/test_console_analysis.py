from __future__ import annotations

import json
from datetime import datetime, timezone

from argus.domain.model import EvidenceRef, Hypothesis
from argus.ports.ports import ModelReply
from argus.console.analysis import analysis_status, analyse

API = "vm-166/container:argus-lab-api"
CACHE = "vm-166/container:argus-lab-cache"


class FakeModel:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def decide(self, messages, tools):
        self.calls.append((messages, tools))
        return ModelReply(text=json.dumps(self.result), tool_calls=[], finish_reason="stop")


def command(**changes):
    return {
        "command_id": "cmd-console-1", "incident_id": "inc-1", "input": "api cpu", "command": "api.cpu",
        "class": "read", "status": "ok", "target": API, "output": ["CPU rose after cache failure"],
        "finished_at": "2026-10-27T10:02:00Z", **changes,
    }


def metric(values, at, target=API):
    return {"target": target, "observed_at": at, "values": values}


def source_model_result(**changes):
    return {
        "evidence": [{"hypothesis_id": "h1", "effect": "contradicts", "reason": "CPU onset is later.",
                      "reference": "after:container_cpu_cores:0"}],
        "comment_sentences": [
            {"text": "The API CPU sample is higher than its earlier sample.",
             "reference": "after:container_cpu_cores:0"},
            {"text": "The recorded cache failure predates this API onset.",
             "reference": "output:0"},
        ],
        "suggestion": "cache status",
        **changes,
    }


def hypotheses_context():
    return {
        "hypotheses": [
            Hypothesis(id="h1", statement="API overload", cause_class="other", target=API, relation="self",
                       status="supported", support=["old-api-observation", "old-api-metric"]),
            Hypothesis(id="h2", statement="Cache failure", cause_class="other", target=CACHE, relation="dependency",
                       status="supported", support=["old-cache-observation"]),
        ],
        "evidence": [
            EvidenceRef(evidence_id="old-api-observation", sha256="0" * 64, capability="api.cpu", status="ok",
                        model_text="cpu", target=API, kind="observation"),
            EvidenceRef(evidence_id="old-api-metric", sha256="1" * 64, capability="api.cpu", status="ok",
                        model_text="cpu metric", target=API, kind="metric_snapshot"),
            EvidenceRef(evidence_id="old-cache-observation", sha256="2" * 64, capability="cache.status", status="ok",
                        model_text="cache stopped", target=CACHE, kind="observation"),
        ],
        "onsets": {
            API: datetime(2026, 10, 27, 10, 1, 30, tzinfo=timezone.utc),
            CACHE: datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc),
        },
        "depends_on": {API: [CACHE]},
    }


def before_after():
    before = [metric({"container_cpu_cores": 0.2}, "2026-10-27T10:00:45Z")]
    after = [metric({"container_cpu_cores": 0.8}, "2026-10-27T10:01:45Z"),
             metric({"container_cpu_cores": 0.9}, "2026-10-27T10:02:00Z")]
    return before, after


def test_analysis_keeps_only_grounded_evidence_validates_suggestion_and_ranks_deterministically():
    result_data = source_model_result(evidence=[
        {"hypothesis_id": "h1", "effect": "contradicts", "reason": "The metric increased.",
         "reference": "after:container_cpu_cores:0"},
        {"hypothesis_id": "h2", "effect": "supports", "reason": "Cache failed first.", "reference": "output:0"},
        {"hypothesis_id": "h1", "effect": "supports", "reason": "Unsupported citation.", "reference": "absent:metric"},
        {"hypothesis_id": "missing-hypothesis", "effect": "supports", "reason": "Unknown hypothesis.",
         "reference": "output:0"},
    ], ranking=[{"id": "h1", "rank": 1}])
    before, after = before_after()

    result = analyse(command(), before, after, hypotheses_context(), FakeModel(result_data))

    assert result.status == "done"
    assert len(result.evidence) == 2
    assert all(item["reference"] in {"output:0", "after:container_cpu_cores:0"} for item in result.evidence)
    assert result.suggestion == {"command": "cache status", "command_id": "cache.status"}
    assert result.comment.count(".") == 2
    ranks = {row.id: row.rank for row in result.ranking}
    assert ranks == {"h1": 2, "h2": 1}
    assert result.hypotheses[0].against[-1] == result.evidence[0]["evidence_id"]


def test_missing_data_returns_an_honest_inconclusive_comment_without_calling_model():
    model = FakeModel(source_model_result())

    result = analyse(command(output=[]), [], [], hypotheses_context(), model)

    assert result.status == "done"
    assert result.evidence == []
    assert result.suggestion is None
    assert "inconclusive" in result.comment.lower()
    assert len(result.comment.split(". ")) in (1, 2, 3)
    assert model.calls == []


def test_invalid_model_suggestion_is_dropped():
    before, after = before_after()
    result = analyse(command(), before, after, hypotheses_context(), FakeModel(source_model_result(suggestion="ls")))
    assert result.suggestion is None


def test_comment_with_missing_or_unsupported_references_uses_grounded_fallback():
    before, after = before_after()
    result = analyse(command(), before, after, hypotheses_context(), FakeModel(source_model_result(
        comment_sentences=[{"text": "This has no source.", "reference": "missing:0"}]
    )))
    assert "inconclusive" in result.comment.lower()
    assert result.comment_references == []


def test_status_waits_for_settle_then_reports_timeout_with_a_retry_command():
    waiting = analysis_status(command(input="cache restart", **{"class": "write", "command": "cache.restart"}), 20, [])
    assert waiting == {"status": "waiting", "countdown_s": 25, "message": None, "retryable": False,
                       "command_id": "cmd-console-1"}
    timeout = analysis_status(command(), 60, [])
    assert timeout == {"status": "error", "countdown_s": None, "message": "Metrics not available yet",
                       "retryable": True, "command_id": "cmd-console-1"}
    ready = analysis_status(command(), 60, before_after()[1])
    assert ready["status"] == "analyzing"


def test_langfuse_exporter_receives_one_command_correlated_span_per_analysis():
    class Exporter:
        def __init__(self):
            self.spans = []

        def submit(self, span):
            self.spans.append(span)

    class Tracing:
        def __init__(self):
            self.exporter = Exporter()

    before, after = before_after()
    tracing = Tracing()
    result = analyse(command(), before, after, hypotheses_context(), FakeModel(source_model_result()),
                     tracing=tracing, started_ns=10, finished_ns=20)
    assert len(tracing.exporter.spans) == 1
    span = tracing.exporter.spans[0]
    attrs = {entry["key"]: entry["value"].get("stringValue") for entry in span["attributes"]}
    assert attrs["argus.command_id"] == "cmd-console-1"
    assert attrs["argus.analysis.status"] == result.status
    assert span["startTimeUnixNano"] == "10" and span["endTimeUnixNano"] == "20"
