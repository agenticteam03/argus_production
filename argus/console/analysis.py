"""Grounded, post-command analysis for the restricted operator console.

The handler supplies plain history, sample, hypothesis, and evidence data. This module does not access the network or
store rows itself: it returns evidence refs and updated hypotheses for the caller to append through IncidentMemoryPort.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from argus.application.ranking import Ranked, first_onsets, rank
from argus.console.parser import ConsoleRefused, parse
from argus.domain.model import EvidenceRef, Hypothesis
from argus.ports.ports import ModelMessage

MAX_OUTPUT_BYTES = 4096
MAX_REASON_CHARS = 500
MAX_COMMENT_CHARS = 1000
_EFFECTS = {"supports", "contradicts", "neutral"}
_SENTENCES = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Analysis:
    status: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    comment: str = ""
    comment_references: list[str] = field(default_factory=list)
    suggestion: dict[str, str] | None = None
    hypotheses: list[Hypothesis] = field(default_factory=list)
    ranking: list[Ranked] = field(default_factory=list)
    error: str | None = None
    retryable: bool = False

    @property
    def order(self) -> list[str]:
        return [row.id for row in self.ranking]


def _read(value: Any, key: str, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _output_lines(command_record: Any) -> list[str]:
    raw = _read(command_record, "output", [])
    lines = raw.splitlines() if isinstance(raw, str) else raw if isinstance(raw, (list, tuple)) else []
    remaining = MAX_OUTPUT_BYTES
    result = []
    for line in lines:
        if remaining <= 0:
            break
        encoded = str(line).encode("utf-8")[:remaining]
        text = encoded.decode("utf-8", errors="ignore")
        result.append(text)
        remaining -= len(encoded)
    return result


def _samples(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict) and isinstance(value.get("samples"), list):
        value = value["samples"]
    if not isinstance(value, (list, tuple)):
        value = [value]
    result = []
    for row in value:
        values = _read(row, "values", None)
        if values is None and isinstance(row, dict):
            values = row
        if not isinstance(values, dict):
            continue
        result.append({"values": values, "target": _read(row, "target"),
                       "observed_at": _read(row, "observed_at")})
    return result


def _sources(command_record: Any, before: Any, after: Any) -> tuple[dict[str, dict], list[str]]:
    sources: dict[str, dict] = {}
    output = _output_lines(command_record)
    target = _read(command_record, "target")
    for index, line in enumerate(output):
        sources[f"output:{index}"] = {"kind": "observation", "target": str(target) if target else None,
                                      "value": line, "observed_at": _read(command_record, "finished_at")}
    for phase, value in (("before", before), ("after", after)):
        for sample_index, sample in enumerate(_samples(value)):
            sample_target = sample["target"] or target
            for signal, metric_value in sample["values"].items():
                if metric_value is None or isinstance(metric_value, (dict, list, tuple)):
                    continue
                ref = f"{phase}:{signal}:{sample_index}"
                sources[ref] = {"kind": "metric_snapshot", "target": str(sample_target) if sample_target else None,
                                "value": metric_value, "observed_at": sample["observed_at"]}
    return sources, output


def _context(hypotheses: Any) -> tuple[list[Hypothesis], list[EvidenceRef], dict, dict]:
    if isinstance(hypotheses, dict):
        rows = hypotheses.get("hypotheses", [])
        evidence_rows = hypotheses.get("evidence", [])
        onsets = hypotheses.get("onsets", {})
        depends_on = hypotheses.get("depends_on", {})
    else:
        rows, evidence_rows, onsets, depends_on = hypotheses or [], [], {}, {}
    parsed_hypotheses = [h if isinstance(h, Hypothesis) else Hypothesis.model_validate(h) for h in rows]
    parsed_evidence = [e if isinstance(e, EvidenceRef) else EvidenceRef.model_validate(e)
                       for e in evidence_rows]
    if isinstance(onsets, list):
        onsets = first_onsets(onsets)
    return parsed_hypotheses, parsed_evidence, onsets if isinstance(onsets, dict) else {}, \
        depends_on if isinstance(depends_on, dict) else {}


def _sentence_parts(text: Any) -> list[str]:
    if not isinstance(text, str):
        return []
    return [part.strip() for part in _SENTENCES.split(text.strip()) if part.strip()]


def _fallback_comment(sources: dict[str, dict]) -> str:
    if not sources:
        return "No command output lines or metric samples were available. The analysis is inconclusive."
    return "The model did not provide a comment with valid source references. The analysis is inconclusive."


def _model_result(model: Any, record: Any, sources: dict[str, dict], hypotheses: list[Hypothesis]) -> dict:
    payload = {
        "command_id": _read(record, "command_id"),
        "input": _read(record, "input"),
        "class": _read(record, "class"),
        "status": _read(record, "status"),
        "sources": [{"reference": ref, "kind": src["kind"], "value": src["value"]}
                    for ref, src in sources.items()],
        "hypotheses": [{"id": h.id, "statement": h.statement, "target": h.target,
                        "status": h.status} for h in hypotheses],
    }
    messages = [
        ModelMessage(role="system", content=(
            "Analyze one completed operator-console command. Use only the supplied sources. Never infer a fact from missing "
            "data. Return JSON with evidence [{hypothesis_id,effect,reason,reference}], comment_sentences "
            "[{text,reference}] (two or three sentences), and optional suggestion (a command string). Every sentence and "
            "evidence entry must cite one exact supplied reference. Do not return a ranking; Python computes it.")),
        ModelMessage(role="user", content=json.dumps(payload, ensure_ascii=False, default=str)),
    ]
    reply = model.decide(messages, [])
    text = _read(reply, "text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("analysis model returned no structured response")
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("analysis model response must be an object")
    return result


def _validated_evidence(model_rows: Any, hypotheses: list[Hypothesis], sources: dict[str, dict],
                        command_id: str) -> tuple[list[dict], list[EvidenceRef], list[Hypothesis]]:
    by_hypothesis = {h.id: h for h in hypotheses}
    changes: list[dict] = []
    refs_by_id: dict[str, EvidenceRef] = {}
    seen: set[tuple[str, str, str]] = set()
    effects: dict[tuple[str, str], str] = {}
    support: dict[str, list[str]] = {h.id: list(h.support) for h in hypotheses}
    against: dict[str, list[str]] = {h.id: list(h.against) for h in hypotheses}
    if not isinstance(model_rows, list):
        return changes, [], hypotheses
    for row in model_rows:
        if not isinstance(row, dict):
            continue
        hypothesis_id = row.get("hypothesis_id")
        effect = row.get("effect")
        reference = row.get("reference")
        reason = row.get("reason")
        if (hypothesis_id not in by_hypothesis or effect not in _EFFECTS or reference not in sources
                or not isinstance(reason, str) or len(_sentence_parts(reason)) != 1):
            continue
        signature = (hypothesis_id, effect, reference)
        relation = (hypothesis_id, reference)
        if signature in seen or relation in effects:
            continue
        seen.add(signature)
        effects[relation] = effect
        source = sources[reference]
        evidence_id = "ev_console_" + hashlib.sha256(f"{command_id}:{reference}".encode()).hexdigest()[:16]
        ref = refs_by_id.get(evidence_id)
        if ref is None:
            text = f"Operator console source {reference}: {source['value']}"
            digest = hashlib.sha256(text.encode()).hexdigest()
            ref = EvidenceRef(evidence_id=evidence_id, sha256=digest, capability="operator_console", status="ok",
                              model_text=text[:MAX_REASON_CHARS], target=source["target"], kind=source["kind"])
            refs_by_id[evidence_id] = ref
        clean_reason = reason.strip()[:MAX_REASON_CHARS]
        changes.append({"hypothesis_id": hypothesis_id, "effect": effect, "reason": clean_reason,
                        "reference": reference, "evidence_id": evidence_id})
        if effect == "supports" and evidence_id not in support[hypothesis_id]:
            support[hypothesis_id].append(evidence_id)
        elif effect == "contradicts" and evidence_id not in against[hypothesis_id]:
            against[hypothesis_id].append(evidence_id)
    updated = [h.model_copy(update={"support": support[h.id], "against": against[h.id]}) for h in hypotheses]
    return changes, list(refs_by_id.values()), updated


def _grounded_comment(value: Any, sources: dict[str, dict]) -> tuple[str, list[str]]:
    rows = value.get("comment_sentences") if isinstance(value, dict) else None
    if not isinstance(rows, list) or not 2 <= len(rows) <= 3:
        return "", []
    sentences, references = [], []
    for row in rows:
        if not isinstance(row, dict):
            return "", []
        text, reference = row.get("text"), row.get("reference")
        if (not isinstance(text, str) or not text.strip() or len(text) > MAX_COMMENT_CHARS
                or "\n" in text or len(_sentence_parts(text)) != 1 or reference not in sources):
            return "", []
        sentence = text.strip()
        if sentence[-1] not in ".!?":
            sentence += "."
        sentences.append(sentence)
        references.append(reference)
    return " ".join(sentences), references


def _suggestion(value: Any) -> dict[str, str] | None:
    candidate = value.get("command") if isinstance(value, dict) else value
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    try:
        parsed = parse(candidate)
    except ConsoleRefused:
        return None
    return {"command": parsed.text, "command_id": parsed.id}


def _trace(tracing: Any, incident_id: str | None, command_id: str, status: str,
           started_ns: int | None, finished_ns: int | None) -> None:
    if tracing is None:
        return
    exporter = getattr(tracing, "exporter", tracing)
    submit = getattr(exporter, "submit", None)
    if not callable(submit):
        return
    start = started_ns if started_ns is not None else time.time_ns()
    end = finished_ns if finished_ns is not None else time.time_ns()
    span = {
        "traceId": uuid.uuid4().hex,
        "spanId": uuid.uuid4().hex[:16],
        "name": "operator.console.analysis",
        "kind": 1,
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(max(start, end)),
        "attributes": [
            {"key": "argus.incident_id", "value": {"stringValue": str(incident_id or "")[:200]}},
            {"key": "argus.command_id", "value": {"stringValue": command_id[:200]}},
            {"key": "argus.analysis.status", "value": {"stringValue": status}},
            {"key": "langfuse.trace.name", "value": {"stringValue": f"operator console {command_id}"[:200]}},
            {"key": "langfuse.observation.type", "value": {"stringValue": "span"}},
        ],
    }
    if status == "error":
        span["status"] = {"code": 2}
    submit(span)


def _finish(result: Analysis, tracing: Any, incident_id: str | None, command_id: str,
            started_ns: int | None, finished_ns: int | None) -> Analysis:
    try:
        _trace(tracing, incident_id, command_id, result.status, started_ns, finished_ns)
    except Exception:  # telemetry must not make command analysis fail
        pass
    return result


def analyse(command_record, before, after, hypotheses, model, *, tracing=None, started_ns=None,
            finished_ns=None) -> Analysis:
    """Return grounded evidence, comment, validated suggestion, and deterministic hypothesis order.

    The `hypotheses` argument may be a list or a bundle containing `hypotheses`, the incident's full `evidence` refs,
    `onsets`, and `depends_on`. The bundle is needed to preserve prior evidence while recomputing the rank.
    """
    command_id = str(_read(command_record, "command_id") or "unknown")
    incident_id = _read(command_record, "incident_id")
    sources, _ = _sources(command_record, before, after)
    try:
        current, old_evidence, onsets, depends_on = _context(hypotheses)
    except Exception:
        current, old_evidence, onsets, depends_on = [], [], {}, {}

    if not sources:
        result = Analysis(status="done", comment=_fallback_comment(sources), hypotheses=current,
                          ranking=rank(current, old_evidence, onsets=onsets, depends_on=depends_on))
        return _finish(result, tracing, incident_id, command_id, started_ns, finished_ns)

    try:
        generated = _model_result(model, command_record, sources, current)
        evidence, new_refs, updated = _validated_evidence(generated.get("evidence"), current, sources, command_id)
        comment, comment_references = _grounded_comment(generated, sources)
        if not comment:
            comment = _fallback_comment(sources)
            comment_references = []
        suggestion = _suggestion(generated.get("suggestion"))
        ordered = sorted(rank(updated, old_evidence + new_refs, onsets=onsets, depends_on=depends_on),
                         key=lambda row: row.rank)
        result = Analysis(status="done", evidence=evidence, comment=comment,
                          comment_references=comment_references, suggestion=suggestion,
                          hypotheses=updated, ranking=ordered)
    except Exception:
        result = Analysis(status="error", comment="The analysis could not be completed. Its result is inconclusive.",
                          hypotheses=current, ranking=rank(current, old_evidence, onsets=onsets, depends_on=depends_on),
                          error="Analysis could not be completed", retryable=True)
    return _finish(result, tracing, incident_id, command_id, started_ns, finished_ns)


def analysis_status(command_record: Any, elapsed_s: float, after: Any) -> dict[str, Any]:
    """Compute the UI state from a command's registered settle delay and collected after-samples."""
    command = None
    try:
        command = parse(str(_read(command_record, "input", ""))).command
    except ConsoleRefused:
        pass
    settle_s = command.settle_s if command else 0
    samples = _samples(after)
    sample_count = len(samples)
    command_id = _read(command_record, "command_id")
    if elapsed_s < settle_s:
        return {"status": "waiting", "countdown_s": max(0, math.ceil(settle_s - elapsed_s)),
                "message": None, "retryable": False, "command_id": command_id}
    if sample_count < 2 and elapsed_s >= 60:
        return {"status": "error", "countdown_s": None, "message": "Metrics not available yet",
                "retryable": True, "command_id": command_id}
    return {"status": "analyzing", "countdown_s": None, "message": None,
            "retryable": False, "command_id": command_id}
