"""The command line: python -m argus.evaluation --cases DIR [--category C ...] [--trials N] [--workdir DIR]

Replays every selected case (offline: no model; step 3 adds the configured model) and prints one line per run, the
§21.2 summary and the hard-rule counts. Exit 0 when every case passes and the hard counts are 0.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from argus.evaluation.cases import load_cases
from argus.evaluation.replay import run_case
from argus.evaluation.score import HARD, grade, hard_violations, summarize


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m argus.evaluation")
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--category", action="append", default=[], help="only these categories (repeatable)")
    p.add_argument("--strategy", default=None, help="run every class with this registered strategy (e.g. baseline)")
    p.add_argument("--trials", type=int, default=1)
    p.add_argument("--workdir", type=Path, default=None, help="throwaway SQLite stores (default: a temp folder)")
    a = p.parse_args(argv)
    cases = [c for c in load_cases(a.cases) if not a.category or c.category in a.category]
    if not cases:
        print("no case selected", file=sys.stderr)
        return 2
    workdir = a.workdir or Path(tempfile.mkdtemp(prefix="argus-eval-"))
    results = []
    for c in cases:
        for i in range(1, a.trials + 1):
            run = run_case(c, workdir, strategy=a.strategy)
            problems = grade(c, run)
            hard = hard_violations(c, run)
            bad = problems + [f"HARD {k}={v}" for k, v in hard.items() if v]
            results.append((c, run))
            print(f"{c.id:<32} {c.category:<17} trial {i}/{a.trials} {'FAIL' if bad else 'PASS'}  "
                  f"{run.outcome} ({run.duration_ms} ms)" + "".join(f"\n    - {x}" for x in bad))
    s = summarize(results)
    fmt = lambda v: "-" if v is None else f"{v:.2f}"                     # noqa: E731
    print(f"cases {s['cases']}  passed {s['passed']}  accuracy {fmt(s['diagnosis_accuracy'])}  "
          f"abstention {fmt(s['safe_abstention'])}  recall@3 {fmt(s['recall_at_3'])}  "
          f"reads/incident {s['reads_per_incident']:.1f}  p50 {s['latency_ms_p50']} ms")
    print("hard: " + " ".join(str(s["hard"][k]) for k in HARD) + "  (" + ", ".join(HARD) + ")")
    return 0 if s["passed"] == s["cases"] and not any(s["hard"].values()) else 1

