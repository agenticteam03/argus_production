"""Re-grade a stored results file with the cases' current labels, without a model call (EVAL-4).

`eval-run.sh` writes one JSON line per run (case, trial, outcome, class, root cause, diagnosis, findings, reads,
passages, audit events, recorded hard counts). When a label changes, the same answers are graded again here, so the
change is measured on the runs that motivated it and not on new ones. The model's requests are not stored, so the
hard counts are the ones recorded at run time.
    python -m argus.evaluation.regrade <results.jsonl> [<cases dir>]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from argus.evaluation.cases import Case, load_cases
from argus.evaluation.replay import CaseRun
from argus.evaluation.score import summarize

CASES = Path(__file__).resolve().parents[2] / "tests" / "eval" / "cases"


def runs_from_file(path: Path, cases: list[Case]) -> list[tuple[Case, CaseRun]]:
    by_id = {c.id: c for c in cases}
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        case = by_id.get(r["case"])
        if case is None:
            raise ValueError(f"{r['case']}: not a case of {sorted(by_id)[:3]}...")
        out.append((case, CaseRun(case_id=r["case"], outcome=r.get("outcome"), incident_class=r.get("incident_class"),
                                  root_cause_target=r.get("root_cause_target"), diagnosis=r.get("diagnosis"),
                                  findings=list(r.get("findings") or []), model_calls=int(r.get("model_calls") or 0),
                                  input_tokens=int(r.get("input_tokens") or 0),
                                  output_tokens=int(r.get("output_tokens") or 0),
                                  reads=[tuple(x) for x in r.get("reads") or []],
                                  passages=[tuple(x) for x in r.get("passages") or []],
                                  audit_events=list(r.get("audit_events") or []),
                                  invalid_decisions=list(r.get("invalid_decisions") or []),
                                  duration_ms=int(r.get("duration_ms") or 0), trial=int(r.get("trial") or 1),
                                  next_actions=list(r.get("next_actions") or []))))
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    cases = load_cases(Path(argv[1]) if len(argv) > 1 else CASES)
    s = summarize(runs_from_file(Path(argv[0]), cases))
    f = lambda v: "n/a" if v is None else f"{v:.2f}"                       # a category absent from the file
    print(f"cases {s['cases']}  passed {s['passed']}  accuracy {f(s['diagnosis_accuracy'])} "
          f"(core {f(s['core_accuracy'])})  abstention {f(s['safe_abstention'])}")
    for name, v in s["per_class"].items():
        print(f"  {name:<34} runs {v['runs']:>3}  accuracy {v['accuracy']:.2f}  worst trial {v['worst_trial']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
