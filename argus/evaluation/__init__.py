"""The §21.2 evaluation (T-0025): replayable cases, the replay harness, grading and the summary.

    python -m argus.evaluation --cases tests/eval/cases [--category C] [--trials N]

A case (`tests/eval/cases/*.yaml`) is a metric snapshot, the answers of the reads it allows, and a label. The harness
replays it through the real wiring (policy, graph, evidence store, redaction) with fixture executors instead of the
target services, then grades the result and the hard checks. It never reaches a VM. Shipped in the image so the
real model's trials (step 3) run in the worker container with the same code.
"""
from argus.evaluation.cases import Case, ExpectedHypotheses, Label, load_cases
from argus.evaluation.replay import CaseRun, run_case
from argus.evaluation.score import (grade, hard_violations, ranking_metrics, recall_at_3, ruled_out_found,
                                    summarize, top_k, unsupported_root_cause)
from argus.evaluation.cli import main

__all__ = ["Case", "CaseRun", "ExpectedHypotheses", "Label", "grade", "hard_violations", "load_cases", "main",
           "ranking_metrics", "recall_at_3", "ruled_out_found", "run_case", "summarize", "top_k",
           "unsupported_root_cause"]
