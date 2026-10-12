# EVAL-3 — An exit 137 without an OOM kill is an unexplained kill: escalate (RB-008)

| Field | Value |
|---|---|
| Status | `in progress` — step 1 (label + baseline, offline) done 2026-10-12; step 2 (the model on the case) with the next evaluation batch |
| Phase | evaluation (§21.2) — [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| Found by | EVAL-2 (#89, `conantkd`): `restart-sigkill-01` escalated 5/5 by the model; listed as "a RB-008 question" |
| Architecture | no change (no ACR): an evaluation label and the §21.2 baseline's rule, aligned with RB-008 |
| Branch | `task/EVAL-3-sigkill-label` (from `main`) |
| Owner | `juanbetancurm` (+ agent); decision by `juanbetancurm`, `conantkd` reviews |
| Needs the VM lease | no (step 2 runs in the next evaluation batch) |

## Goal (plain language)

The worker restarts with exit 137 (SIGKILL) and `oom_killed: false`; its logs and the kernel OOM records show nothing
else. Something outside the container killed it, and nothing in the evidence says what. The case was labelled
`diagnosed` with **the worker itself** as root cause, which names the victim of the kill as its cause. RB-008, written
before the evaluation, says the opposite:

- "Absence of retained OOM evidence does not prove a non-OOM cause; preserve uncertainty for unexplained kills."
- Workflow step 1: "Unknown kill → retain OOM/external alternatives."
- Decision tree: "unexplained → multiple_hypotheses / insufficient_evidence"; edge cases: "signal kills without OOM
  evidence".

So the model's 5/5 escalation in EVAL-2 followed the runbook. The label and the baseline change; RB-008 does not.

## Step 1 (done, offline)

- `tests/eval/cases/restart-sigkill-01.yaml`: label `no_action_escalated`, `abstain: true`, no root cause, RB-008.
  **The fixtures are unchanged.** The label changed after seeing the model's answers; RB-008's text predates them.
- `BaselineStrategy._restart`: exit 137 without an OOM kill decides nothing, so the baseline escalates. It still names
  an OOM kill (RB-001) and an application crash with its exit code.
- Tests: `tests/test_eval3_sigkill.py` (3; red seen 2/3: the baseline answered `diagnosed`). The evaluation, EVAL-2,
  E2E-5 and T-0019 batch 2 suites pass (138, 1 skipped); `brain.py lint` clean.
- Baseline: 55 cases, 52 pass (the three declared misses), `container_restart_loop` 0.83, hard 0 0 0: unchanged.

## Step 2 (the next evaluation batch)

The configured model on the 55 cases: `restart-sigkill-01` is expected to pass where it escalates, as in EVAL-2.

## Rejected alternative

Change RB-008 so that exit 137 without OOM names the container. Rejected: it makes Argus blame the victim of an outside
kill, against the runbook's own uncertainty rule.
