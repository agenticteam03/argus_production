## 2026-10-22 — T-0049 R1b: container process replay fixtures

Type: code (offline; no class offer)
Who: S4, with S1 pre-review
Context: S2's second R1 candidate is `container.processes` (`processes`) for `container_restart_loop`. The six labelled
restart cases lacked `/containers/<name>/top` fixtures, so replay failed before the candidate read could be measured.
Decision / result:
- Added `/top` fixtures to all six restart cases in the T-0037 gateway shape: PID, PPID, command name, count and
  collection time. Each PID and command match the live worker row in that case's host `/processes` fixture. OOM cases
  retain the killed earlier PIDs; the exit-0 job shows a relaunched Python process while its logs say `done`. The class
  offer remains a separate measured step.
Consequences: Replays are complete, but `container.processes` reports only count and command names. All six cases show
one Python process, so the read cannot distinguish an OOM kill, an exit-0 job or a crash. Logs, exit code and memory
history do distinguish them. Expected gain from offering this read to `container_restart_loop` is low; no class offer
was made.

### Test state

- Red first: the six replay assertions failed because `/containers/argus-lab-worker/top` was missing and the fixture
  executor raised `ExecutorError: not_found`.
- On the branch before the latest main update, the R1b, T-0037 and evaluation tests passed; Ruff and Brain lint/audit
  were clean. The full offline suite passed once after S1's rule-7 pre-review.
- Brain's `split_entry` accepted the corrected heading and extracted the Test state and Next step sections.
- R1BF.1 reruns the focused R1b, T-0037 and evaluation tests, Ruff, Brain lint/audit, `split_entry` and diff-check after
  merging current main. The full suite is not repeated for this journal-only correction.

### Next step

R1BF.1 commits this correction and merges current `origin/main` into the existing branch with a merge commit. After the
focused checks pass, the developer-run block pushes the branch and comments on #300 for conantkd's re-review.
