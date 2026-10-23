# T-0049 R1b: container process replay fixtures

### Change

Prepared S2's second R1 candidate, `container.processes` (`processes`) for `container_restart_loop`. The six labelled
restart cases now have `/containers/<name>/top` fixtures in the T-0037 gateway shape: PID, PPID, command name only,
count, and collection time. Each `/top` PID and command matches the live worker row in that case's host `/processes`
fixture. In the OOM cases, PID 4242 is the current worker, while the host OOM records name the killed earlier PIDs;
the exit-0 job shows the relaunched Python process while its existing log still records `done`. The branch was
fast-forwarded to current main b22c669 (#296/#297); the task note retains both the shared-ID skill update and the R1b
candidate preparation. No detector or class offer changed; the offer remains a separate measured R1 step.

### Finding

The real `container.processes` read returns a process count and command names. It shows the same result, one `python`
process, in all six restart cases, so it cannot distinguish an OOM kill, an exit-0 job, or a crash. The existing logs,
exit code, and memory history distinguish those causes. The expected gain from offering this read to
`container_restart_loop` is low; the fixtures still make the replays complete instead of failing with a missing-read
error.

### Test state

- Red first: the six new replay assertions failed because `/containers/argus-lab-worker/top` was missing and the
  fixture executor raised `ExecutorError: not_found`.
- Green: the focused six-case replay test passes, including the check that `/top` matches the current host process
  row; the combined T-0037, EVAL-3, and R1b tests pass. After the b22c669 refresh, the R1b test, `test_evaluation.py`,
  T-0037, and EVAL-3 replay regressions passed again (pytest reached 100%, exit 0). Ruff and Brain lint/audit are clean;
  `git diff --check` is clean.
- Full offline suite: one run with Git Bash first on `PATH`, after S1's clear rule-7 pre-review; pytest reached 100%
  and exited 0. The progress output included skipped tests and no failures.

### Next step

Main moved to b22c669 (#296/#297); the branch was fast-forwarded and the task note retains both main's shared-ID
update and this candidate-preparation section. S4R1B.1 pins b22c669 and requires it to remain an ancestor of
`origin/main`. The focused replay regressions, Ruff, Brain lint/audit, whitespace, `check_block.py`, and PowerShell
parser pass on this refreshed tree. Post READY with the finding above. The developer-run block stages only the six
case fixtures, this test, the T-0049 task note, and this journal entry; S4 does not run it.
