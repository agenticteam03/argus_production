## 2026-10-21 — main-guard: a 15-minute limit instead of 5

Type: process
Who: juanbetancurm (+ agent)
Context: the `main-guard` run after #226 (main `f3d831c`) was cancelled at its 5-minute limit while `brain.py
verify-main` waited on GitHub's API; nothing was red. `verify-main` asks GitHub about every merge on `main` (222
first-parent commits today, several calls each), and the runs before took 3.5 to 4.5 minutes, so a slow API is enough
to cross the limit. Run locally the same day, the same calls stalled at random and answered in a second when retried.
Decision / result:
- `.github/workflows/ci.yml`: `main-guard` gets `timeout-minutes: 15`. The rule it checks is unchanged.
Consequences: a cancelled `main-guard` is still not a pass: it is re-run, and a merge waits for it to be green. The run
time grows with every merge; if it nears 15 minutes, `verify-main` could check only the commits since the last green
run, which changes the enforcement and needs its own review.
References: [REVIEW_PROTOCOL](../../agents/REVIEW_PROTOCOL.md), #226.
