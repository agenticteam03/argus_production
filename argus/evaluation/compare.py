"""Compare two offline, paired evaluation result files."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from argus.evaluation.cases import Case, load_cases
from argus.evaluation.replay import CaseRun
from argus.evaluation.score import grade

HARD_KINDS = ("actions_outside_policy", "secrets_in_model_requests", "forbidden_target_reads",
              "unsupported_root_cause")
_REQUIRED = ("case", "category", "trial", "model", "strategy", "outcome", "incident_class",
             "root_cause_target", "diagnosis", "findings", "model_calls", "duration_ms", "hard",
             "hypothesis_problems")


def hypothesis_problem_kind(message: str) -> str:
    """Map H1's stable problem phrases to report buckets; keep unknown phrases visible as unclassified."""
    text = message.lower()
    rules = (
        ("hypotheses must be a list", "invalid_hypotheses_value"),
        ("hypotheses: at most", "too_many_hypotheses"),
        ("fails its schema", "schema_invalid"),
        ("the same id twice", "duplicate_id"),
        ("cites evidence not stored", "unknown_evidence"),
        ("same evidence both for and against", "conflicting_evidence"),
        ("no target, but its relation", "invalid_target_relation"),
        ("target ", "target_out_of_scope"),
        ("external cause supported without an observation", "external_without_observation"),
        ("supported without an observation", "supported_without_observation"),
        ("ruled out without evidence against", "ruled_out_without_against"),
        ("a conclusion without hypotheses", "conclusion_without_hypotheses"),
        ("a root_cause_target without a chosen hypothesis", "root_cause_without_chosen"),
        ("chosen ", "chosen_other"),
    )
    for phrase, kind in rules:
        if phrase not in text:
            continue
        if kind == "target_out_of_scope" and "not in the incident's scope" not in text:
            continue
        if kind == "chosen_other":
            if "is not one of the hypotheses" in text:
                return "chosen_id_unknown"
            if "is external:" in text:
                return "chosen_external"
            if ", not supported" in text:
                return "chosen_not_supported"
            if "not the root_cause_target" in text:
                return "chosen_target_mismatch"
            continue
        return kind
    return "unclassified"


def _bad(path: Path, line: int, message: str) -> ValueError:
    return ValueError(f"{path.name}:{line}: {message}")


def _integer(value: Any, name: str, path: Path, line: int, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _bad(path, line, f"{name} must be an integer >= {minimum}")
    return value


def _optional_string(value: Any, name: str, path: Path, line: int) -> str | None:
    if value is not None and not isinstance(value, str):
        raise _bad(path, line, f"{name} must be a string or null")
    return value


def _read_rows(path: Path, by_id: dict[str, Case]) -> dict[tuple[str, int], dict[str, Any]]:
    rows: dict[tuple[str, int], dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path}: result file is not valid UTF-8") from exc
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    for number, text in enumerate(lines, start=1):
        if not text.strip():
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError as exc:
            raise _bad(path, number, f"invalid JSON: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise _bad(path, number, "row must be a JSON object")
        missing = [key for key in _REQUIRED if key not in row]
        if missing:
            raise _bad(path, number, f"missing required fields: {', '.join(missing)}")
        case_id = row["case"]
        if not isinstance(case_id, str) or not case_id:
            raise _bad(path, number, "case must be a non-empty string")
        case = by_id.get(case_id)
        if case is None:
            raise _bad(path, number, f"unknown case {case_id!r}")
        if row["category"] != case.category:
            raise _bad(path, number, f"category does not match case {case_id!r}")
        trial = _integer(row["trial"], "trial", path, number, minimum=1)
        for name in ("model", "strategy"):
            if not isinstance(row[name], str) or not row[name].strip():
                raise _bad(path, number, f"{name} must be a non-empty string")
        for name in ("outcome", "incident_class", "root_cause_target", "diagnosis"):
            _optional_string(row[name], name, path, number)
        for name in ("findings", "hypothesis_problems"):
            if not isinstance(row[name], list) or any(not isinstance(item, str) for item in row[name]):
                raise _bad(path, number, f"{name} must be a list of strings")
        _integer(row["model_calls"], "model_calls", path, number)
        _integer(row["duration_ms"], "duration_ms", path, number)
        hard = row["hard"]
        if not isinstance(hard, dict):
            raise _bad(path, number, "hard must be an object of failure counts")
        missing_hard = [name for name in HARD_KINDS if name not in hard]
        if missing_hard:
            raise _bad(path, number, f"hard is missing kinds: {', '.join(missing_hard)}")
        for name, value in hard.items():
            if not isinstance(name, str):
                raise _bad(path, number, "hard kind names must be strings")
            _integer(value, f"hard.{name}", path, number)
        for name in ("input_tokens", "output_tokens"):
            if name in row and row[name] is not None:
                _integer(row[name], name, path, number)
        for name in ("problems",):
            if name in row and (not isinstance(row[name], list) or any(not isinstance(x, str) for x in row[name])):
                raise _bad(path, number, f"{name} must be a list of strings")
        key = (case_id, trial)
        if key in rows:
            raise _bad(path, number, f"duplicate case/trial row {case_id!r} trial {trial}")
        rows[key] = row
    if not rows:
        raise ValueError(f"{path}: no result rows")
    return rows


def _metadata(rows: dict[tuple[str, int], dict[str, Any]], arm: str) -> dict[str, str]:
    values = {name: {row[name] for row in rows.values()} for name in ("model", "strategy")}
    for name, choices in values.items():
        if len(choices) != 1:
            raise ValueError(f"{arm} arm has mixed {name} metadata: {sorted(choices)}")
    return {name: next(iter(choices)) for name, choices in values.items()}


def _case_run(case_id: str, row: dict[str, Any]) -> CaseRun:
    return CaseRun(case_id=case_id, outcome=row["outcome"], incident_class=row["incident_class"],
                   root_cause_target=row["root_cause_target"], diagnosis=row["diagnosis"], findings=row["findings"],
                   model_calls=row["model_calls"], reads=[], passages=[], audit_events=[],
                   duration_ms=row["duration_ms"], trial=row["trial"])


def _arm_report(rows: dict[tuple[str, int], dict[str, Any]], cases: dict[str, Case]) -> dict[str, Any]:
    correct: dict[str, list[bool]] = {}
    hard = Counter({key: 0 for key in HARD_KINDS})
    hyp = Counter({"unclassified": 0})
    unclassified = Counter()
    model_calls = 0
    input_tokens: list[int | None] = []
    output_tokens: list[int | None] = []
    durations: list[int] = []
    for (case_id, _), row in rows.items():
        case = cases[case_id]
        if case.category == "class":
            expected_class = case.label.incident_class
            if not expected_class:
                raise ValueError(f"case {case_id!r}: class category has no expected class label")
            correct.setdefault(expected_class, []).append(not grade(case, _case_run(case_id, row)))
        for kind, count in row["hard"].items():
            hard[kind] += count
        for message in row["hypothesis_problems"]:
            kind = hypothesis_problem_kind(message)
            hyp[kind] += 1
            if kind == "unclassified":
                unclassified[message] += 1
        model_calls += row["model_calls"]
        input_tokens.append(row.get("input_tokens"))
        output_tokens.append(row.get("output_tokens"))
        durations.append(row["duration_ms"])
    per_class = {name: {"runs": len(values), "correct": sum(values), "accuracy": sum(values) / len(values)}
                 for name, values in sorted(correct.items())}

    def token_total(values: list[int | None]) -> int | None:
        if all(value is not None for value in values):
            return sum(value for value in values if value is not None)
        return None

    return {
        "runs": len(rows),
        "per_class": per_class,
        "hard_failures": dict(sorted(hard.items())),
        "hypothesis_problems": dict(sorted(hyp.items())),
        "unclassified_messages": dict(sorted(unclassified.items())),
        "model_calls": model_calls,
        "input_tokens": token_total(input_tokens),
        "output_tokens": token_total(output_tokens),
        "token_rows_missing": {"input_tokens": sum(v is None for v in input_tokens),
                                "output_tokens": sum(v is None for v in output_tokens)},
        # Match summarize()'s middle order statistic so paired reports use the evaluator's p50 convention.
        "latency_ms_p50": sorted(durations)[len(durations) // 2],
    }


def compare_files(before: Path, after: Path, cases_dir: Path) -> dict[str, Any]:
    """Validate identical `(case, trial)` arms and summarize measurements against the supplied labels."""
    cases_list = load_cases(cases_dir)
    cases = {case.id: case for case in cases_list}
    before_rows = _read_rows(before, cases)
    after_rows = _read_rows(after, cases)
    before_keys, after_keys = set(before_rows), set(after_rows)
    if before_keys != after_keys:
        missing_after = sorted(before_keys - after_keys)
        missing_before = sorted(after_keys - before_keys)
        raise ValueError(f"coverage mismatch: missing in after={missing_after}; missing in before={missing_before}")
    before_meta = _metadata(before_rows, "before")
    after_meta = _metadata(after_rows, "after")
    if before_meta != after_meta:
        raise ValueError(f"metadata mismatch: before={before_meta}; after={after_meta}")
    return {"metadata": before_meta,
            "before": _arm_report(before_rows, cases),
            "after": _arm_report(after_rows, cases)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m argus.evaluation.compare")
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = compare_files(args.before, args.after, args.cases)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
