"""The command line: python -m argus.evaluation --cases DIR [--category C ...] [--trials N] [--workdir DIR]

Replays every selected case (offline: no model; step 3 adds the configured model) and prints one line per run, the
§21.2 summary and the hard-rule counts. Exit 0 when every case passes and the hard counts are 0.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from argus.evaluation.cases import load_cases
from argus.evaluation.replay import run_case
from argus.evaluation.score import HARD, grade, hard_violations, summarize
from argus.infrastructure.wiring import Settings, make_llm


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m argus.evaluation")
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--category", action="append", default=[], help="only these categories (repeatable)")
    p.add_argument("--strategy", default=None, help="run every class with this registered strategy (e.g. baseline)")
    p.add_argument("--model", choices=["none", "configured"], default="none",
                   help="none: no model (offline); configured: the model the worker uses (key from ARGUS_SECRETS_DIR)")
    p.add_argument("--out", type=Path, default=None, help="append one JSON line per run to this file")
    p.add_argument("--trials", type=int, default=1)
    p.add_argument("--workdir", type=Path, default=None, help="throwaway SQLite stores (default: a temp folder)")
    a = p.parse_args(argv)
    cases = [c for c in load_cases(a.cases) if not a.category or c.category in a.category]
    if not cases:
        print("no case selected", file=sys.stderr)
        return 2
    llm = None
    if a.model == "configured":
        llm = make_llm(Settings())
        if llm is None:
            print("no model configured: no openai_api_key in ARGUS_SECRETS_DIR and no OPENAI_API_KEY", file=sys.stderr)
            return 2
    workdir = a.workdir or Path(tempfile.mkdtemp(prefix="argus-eval-"))
    results = []
    for c in cases:
        for i in range(1, a.trials + 1):
            run = run_case(c, workdir, llm=llm, strategy=a.strategy)
            run.trial = i
            problems = grade(c, run)
            hard = hard_violations(c, run)
            bad = problems + [f"HARD {k}={v}" for k, v in hard.items() if v]
            results.append((c, run))
            if a.out:
                a.out.parent.mkdir(parents=True, exist_ok=True)
                row = {"case": c.id, "category": c.category, "strategy": a.strategy or "registered",
                       "model": a.model, "verdict": "FAIL" if bad else "PASS", "problems": problems, "hard": hard,
                       **{k: v for k, v in asdict(run).items() if k not in ("model_requests", "case_id")}}
                with a.out.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{c.id:<32} {c.category:<17} trial {i}/{a.trials} {'FAIL' if bad else 'PASS'}  "
                  f"{run.outcome} ({run.duration_ms} ms)" + "".join(f"\n    - {x}" for x in bad))
    s = summarize(results)
    fmt = lambda v: "-" if v is None else f"{v:.2f}"                     # noqa: E731
    print(f"cases {s['cases']}  passed {s['passed']}  accuracy {fmt(s['diagnosis_accuracy'])}  "
          f"abstention {fmt(s['safe_abstention'])}  recall@3 {fmt(s['recall_at_3'])}  "
          f"reads/incident {s['reads_per_incident']:.1f}  p50 {s['latency_ms_p50']} ms")
    for cls, v in s["per_class"].items():
        print(f"  {cls:<34} runs {v['runs']:>3}  accuracy {v['accuracy']:.2f}  worst trial {v['worst_trial']:.2f}")
    print("hard: " + " ".join(str(s["hard"][k]) for k in HARD) + "  (" + ", ".join(HARD) + ")")
    return 0 if s["passed"] == s["cases"] and not any(s["hard"].values()) else 1

