## 2026-10-22 — T-0049 S5: first evidence for the skills

Type: evaluation draft (documentation only)
Who: juanbetancurm (+ agent)
Context: T-0049 S5, branch `task/T-0049-s5-evaluation`, with evidence drafted from main `aa6d75a` after fast-forwarding
from `f480152`; after review, the worktree fast-forwarded to `7a634c7` (#290 and #274 merged). S1 owns the T-0049
Status row; it is unchanged.

Decision / result:
- Fill the P0/P1 evaluation table from recorded PRs, board messages and journals only. All with/without task counts
  remain "not measured yet": implementation tests and reviewer rounds are not controlled task comparisons.
- Record observed corrections and traps for `code-bash-step` (#275), `pr-review` (#277), `acr-and-version-line`
  (#281), `add-capability` (#285) and `db-migration` (#286). The records show useful checker catches, and also
  rework: code-bash template/checker corrections, a paired-review wording fix and self-review logic fix for
  `pr-review`, a checker-test correction after #274 offered `analysis.anomaly_summary` to
  `container_restart_loop` (FIX.274; 1727 tests passed), and a migration-number fixture correction after #280 added
  migration 013.
- Add P2 observations for `journal-and-task-status` (#283), `vm-deploy` (#289), and `ui-contract-samples` (#290)
  with the real sample refresh PR #291. The latter caught stale same-shape samples but still had to restore IDs shared
  with other samples after Playwright failed.
- Propose three matched tasks per P0/P1 skill, with fresh sessions, randomized order, blinded review, manual
  activation checks, and records of corrections, failed blocks, checker false positives, and time to review-ready.
- Record costs separately from task counts: the code-bash journal includes checker false positives and guard/marker
  fixture failures; #277 needed wording and self-merge fixes; the add-capability checker test was pinned to main's
  unoffered state and #274 CI went red until S1 fixed its test line (FIX.274); #283 needed status-format and `done`-guard
  corrections; #286 needed a fixture-number update after #280. No record counts developer-run blocks failed by these
  skills.

Consequences:
The evidence supports keeping these skills provisionally, not claiming measured net benefit. S5 should update the
counts after paired runs and remove any skill whose observed rework exceeds its value. PR #290 merged on 2026-10-22;
#291 is still open. No skill-selection or effectiveness counts were inferred from them.

References: T-0049; PRs #275, #277, #281, #283, #285, #286, #289, #290, #291; `SESSIONS.md` and
`SESSIONS-archive-2026-10-22.md` board records.

### Test state

- Documentation-only draft; no runtime or skill code changed. Brain lint and audit are clean; `git diff --check` is
  clean. The isolated S5.1 block passes `check_block.py` and parses with zero PowerShell errors without execution.
- No full offline suite was run, as requested for documentation-only changes.

### Next step

After review, run the proposed three paired tasks per P0/P1 skill, record evidence without changing measured counts
from the records in this draft, then decide whether any skill should be removed.
