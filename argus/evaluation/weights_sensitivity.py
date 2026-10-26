"""Re-rank recorded evaluation rows under one-at-a-time ACR-0024 weight changes.

Rows are scorable only when they retain hypothesis support/against ids and the evidence records
(evidence_id, kind, target) needed by argus.application.ranking.rank. The stored rank is ignored.
`peer_finding` is swept like the other weights but is inert today: rank() cites no peer finding by evidence id, so its
half and double sets always equal `current`.
    python -m argus.evaluation.weights_sensitivity --cases tests/eval/cases <results.jsonl> [...]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

from argus.application.ranking import Weights, load_ranking, rank, ranking_disagrees
from argus.evaluation.cases import Case, load_cases

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = ROOT / "tests" / "eval" / "cases"
WEIGHT_FIELDS = (
    "own_observation", "own_metric_snapshot", "other_observation", "alert", "peer_finding", "reported_symptom",
)


def weight_sets(current: Weights) -> dict[str, Weights]:
    """Current weights, each score weight halved/doubled alone, plus the requested penalty endpoints."""
    variants = {"current": current}
    for name in WEIGHT_FIELDS:
        value = getattr(current, name)
        variants[f"{name}_half"] = replace(current, **{name: value / 2})
        variants[f"{name}_double"] = replace(current, **{name: value * 2})
    variants["untested_penalty_0"] = replace(current, untested_penalty=0.0)
    variants["untested_penalty_1"] = replace(current, untested_penalty=1.0)
    return variants


def _ratio(correct: int, total: int) -> dict:
    return {"correct": correct, "total": total, "accuracy": correct / total if total else None}


def _prepare(row: dict) -> tuple[list[SimpleNamespace], list[SimpleNamespace], str | None] | str:
    raw_hypotheses = row.get("hypotheses")
    if not isinstance(raw_hypotheses, list) or not raw_hypotheses:
        return "missing hypotheses"
    hypotheses = []
    for index, raw in enumerate(raw_hypotheses):
        if not isinstance(raw, dict):
            return f"hypotheses[{index}] is not an object"
        required = ("id", "target", "cause_class", "status", "support", "against")
        missing = [key for key in required if key not in raw]
        if missing:
            return f"hypotheses[{index}] missing {','.join(missing)}"
        if (not isinstance(raw["id"], str) or not isinstance(raw["cause_class"], str)
                or raw["status"] not in ("supported", "ruled_out", "untested")
                or not isinstance(raw["support"], list) or not all(isinstance(x, str) for x in raw["support"])
                or not isinstance(raw["against"], list) or not all(isinstance(x, str) for x in raw["against"])
                or (raw["target"] is not None and not isinstance(raw["target"], str))):
            return f"hypotheses[{index}] has invalid ranking fields"
        hypotheses.append(SimpleNamespace(id=raw["id"], target=raw["target"], cause_class=raw["cause_class"],
                                           status=raw["status"], support=raw["support"], against=raw["against"]))
    if len({h.id for h in hypotheses}) != len(hypotheses):
        return "duplicate hypothesis ids"

    raw_evidence = row.get("evidence")
    if not isinstance(raw_evidence, list):
        return "missing evidence records"
    evidence = []
    for index, raw in enumerate(raw_evidence):
        if not isinstance(raw, dict):
            return f"evidence[{index}] is not an object"
        missing = [key for key in ("evidence_id", "kind", "target") if key not in raw]
        if missing:
            return f"evidence[{index}] missing {','.join(missing)}"
        if (not isinstance(raw["evidence_id"], str)
                or (raw["kind"] is not None and not isinstance(raw["kind"], str))
                or (raw["target"] is not None and not isinstance(raw["target"], str))):
            return f"evidence[{index}] has invalid ranking fields"
        evidence.append(SimpleNamespace(evidence_id=raw["evidence_id"], kind=raw["kind"], target=raw["target"]))

    chosen_flags = [h["id"] for h in raw_hypotheses if h.get("chosen") is True]
    if len(chosen_flags) > 1:
        return "multiple chosen hypotheses"
    chosen = row.get("chosen")
    if not isinstance(chosen, str):
        chosen = chosen_flags[0] if chosen_flags else None
    if chosen is not None and (chosen not in {h.id for h in hypotheses}
                               or (chosen_flags and chosen_flags != [chosen])):
        return "chosen id not in hypotheses"
    return hypotheses, evidence, chosen


def _matches(hypothesis: SimpleNamespace, expected: str) -> bool:
    return expected in (hypothesis.target, hypothesis.cause_class)


def rank_recorded_row(row: dict, weights: Weights | None = None) -> dict[str, int]:
    """Return the rank() output for one fully recorded result row, keyed by hypothesis id.

    This deliberately uses the same parsed support/against and evidence inputs as the sensitivity analyzer.
    """
    parsed = _prepare(row)
    if isinstance(parsed, str):
        raise ValueError(f"row is not scorable: {parsed}")
    hypotheses, evidence, _ = parsed
    return {item.id: item.rank for item in rank(hypotheses, evidence, weights or Weights())}


def _blank_metrics() -> dict:
    return {"top1_correct": 0, "top1_total": 0, "top3_correct": 0, "top3_total": 0,
            "ruled_out_found": 0, "ruled_out_expected": 0, "disagrees": 0, "disagrees_total": 0}


def _finish_metrics(metrics: dict, *, include_classes: bool = False) -> dict:
    result = {
        "top1": _ratio(metrics["top1_correct"], metrics["top1_total"]),
        "top3": _ratio(metrics["top3_correct"], metrics["top3_total"]),
        "ruled_out_recall": {"found": metrics["ruled_out_found"], "expected": metrics["ruled_out_expected"],
                             "recall": (metrics["ruled_out_found"] / metrics["ruled_out_expected"]
                                        if metrics["ruled_out_expected"] else None)},
        "ranking_disagrees": {"count": metrics["disagrees"], "total": metrics["disagrees_total"]},
    }
    if include_classes:
        result["per_class"] = {
            name: {**_finish_metrics(values), "rows": values["rows"], "not_scorable": values["not_scorable"]}
            for name, values in sorted(metrics["per_class"].items())
        }
    return result


def analyze_rows(rows: Iterable[dict], cases: dict[str, Case], current: Weights | None = None) -> dict:
    """Recompute rankings and class metrics. Rows without full ranking inputs are reported, never imputed."""
    current = current or Weights()
    variants = weight_sets(current)
    prepared: list[tuple[Case, list[SimpleNamespace], list[SimpleNamespace], str | None]] = []
    reasons: Counter[str] = Counter()
    rows_by_class: Counter[str] = Counter()
    unscorable_by_class: Counter[str] = Counter()
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            reasons["row is not an object"] += 1
            continue
        case_id = row.get("case", row.get("case_id"))
        if not isinstance(case_id, str) or case_id not in cases:
            raise ValueError(f"row {number}: unknown or missing case id {case_id!r}")
        case = cases[case_id]
        class_name = case.label.incident_class or case.category
        rows_by_class[class_name] += 1
        parsed = _prepare(row)
        if isinstance(parsed, str):
            reasons[parsed] += 1
            unscorable_by_class[class_name] += 1
            continue
        prepared.append((case, *parsed))

    results = {}
    for name, weights in variants.items():
        total = _blank_metrics()
        total["per_class"] = {class_name: _blank_metrics() for class_name in sorted(rows_by_class)}
        for case, hypotheses, evidence, chosen in prepared:
            ranked = rank(hypotheses, evidence, weights)
            rank_by_id = {item.id: item.rank for item in ranked}
            class_name = case.label.incident_class or case.category
            metrics = total["per_class"].setdefault(class_name, _blank_metrics())
            expected_causes = case.label.expected_causes()
            if expected_causes:
                top1 = any(rank_by_id[h.id] == 1 and any(_matches(h, e) for e in expected_causes)
                           for h in hypotheses)
                top3 = any(rank_by_id[h.id] <= 3 and any(_matches(h, e) for e in expected_causes)
                           for h in hypotheses)
                for target in (total, metrics):
                    target["top1_correct"] += int(top1)
                    target["top1_total"] += 1
                    target["top3_correct"] += int(top3)
                    target["top3_total"] += 1
            expected_hypotheses = case.label.expected_hypotheses
            ruled_out = expected_hypotheses.ruled_out if expected_hypotheses else []
            if ruled_out:
                found = sum(any(h.status == "ruled_out" and _matches(h, expected) for h in hypotheses)
                            for expected in ruled_out)
                for target in (total, metrics):
                    target["ruled_out_found"] += found
                    target["ruled_out_expected"] += len(ruled_out)
            disagrees = ranking_disagrees(ranked, chosen)
            for target in (total, metrics):
                target["disagrees"] += int(disagrees)
                target["disagrees_total"] += 1
        for class_name, metrics in total["per_class"].items():
            metrics["rows"] = rows_by_class[class_name]
            metrics["not_scorable"] = unscorable_by_class[class_name]
        results[name] = _finish_metrics(total, include_classes=True)

    return {"rows": len(prepared) + sum(reasons.values()), "scorable": len(prepared),
            "not_scorable": sum(reasons.values()), "not_scorable_reasons": dict(sorted(reasons.items())),
            "not_scorable_by_class": dict(sorted(unscorable_by_class.items())), "sets": results}


def _fmt_ratio(value: dict, key: str = "correct") -> str:
    total = value["total"]
    return "n/a" if not total else f"{value[key]}/{total} ({value['accuracy']:.3f})"


def _fmt_recall(value: dict) -> str:
    return ("n/a" if value["expected"] == 0 else
            f"{value['found']}/{value['expected']} ({value['recall']:.3f})")


def render_report(name: str, summary: dict) -> str:
    lines = [f"result file: {name} | rows {summary['rows']} | scorable {summary['scorable']} | "
             f"not scorable {summary['not_scorable']}"]
    if summary["not_scorable_reasons"]:
        reasons = "; ".join(f"{reason}: {count}" for reason, count in summary["not_scorable_reasons"].items())
        lines.append(f"not-scorable reasons: {reasons}")
    lines.append("weight set | top-1 | top-3 | ruled-out recall | ranking_disagrees")
    for set_name, metrics in summary["sets"].items():
        top1, top3, ruled, disagree = (metrics[k] for k in ("top1", "top3", "ruled_out_recall", "ranking_disagrees"))
        lines.append(f"{set_name} | {_fmt_ratio(top1)} | {_fmt_ratio(top3)} | {_fmt_recall(ruled)} | "
                     f"{disagree['count']}/{disagree['total']}")
        for class_name, class_metrics in metrics["per_class"].items():
            scorable = class_metrics["rows"] - class_metrics["not_scorable"]
            lines.append(f"  class {class_name}: scorable {scorable}/{class_metrics['rows']}; "
                         f"not scorable {class_metrics['not_scorable']}; top-1 {_fmt_ratio(class_metrics['top1'])}; "
                         f"top-3 {_fmt_ratio(class_metrics['top3'])}; "
                         f"ruled-out {_fmt_recall(class_metrics['ruled_out_recall'])}; "
                         f"ranking_disagrees {class_metrics['ranking_disagrees']['count']}/"
                         f"{class_metrics['ranking_disagrees']['total']}")
    return "\n".join(lines)


def _read_rows(path: Path) -> list[dict]:
    rows = []
    stream = sys.stdin if path == Path("-") else path.open(encoding="utf-8")
    try:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number}: invalid JSON: {exc.msg}") from exc
    finally:
        if path != Path("-"):
            stream.close()
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="evaluation case directory")
    parser.add_argument("--stdin-name", default="stdin.jsonl", help="display name when a result is read from stdin")
    parser.add_argument("results", nargs="+", type=Path, help="read-only JSONL run files")
    args = parser.parse_args(argv)
    cases = {case.id: case for case in load_cases(args.cases)}
    current = load_ranking(ROOT / "config")
    if sum(path == Path("-") for path in args.results) > 1:
        parser.error("use stdin for at most one result file per invocation")
    for path in args.results:
        name = args.stdin_name if path == Path("-") else path.name
        print(render_report(name, analyze_rows(_read_rows(path), cases, current)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
