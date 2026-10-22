## 2026-10-22 — T-0049 S3: ACR and architecture version-line skill

Type: implementation
Who: juanbetancurm (+ agent)
Context: T-0049 S3, first P1 skill, branch `task/T-0049-s3-acr-version-line`
from main `9d8963b`, then fast-forwarded to main `6a72339` after #275 merged.
The shared T-0049 task row is owned by S1 after the parallel skill PRs merge.

Decision / result:
- The skill reads the live ACR template and Brain protocol. A proposal stays
  proposed; only the recorded human decision permits the agreed architecture
  change in the implementation PR.
- `version_line.py` reads two architecture snapshots and prints reviewable
  version-header and changelog replacements. It retains both branches'
  versions, sorts numerically, and rejects conflicting reuse or lost rows.
  It never edits the architecture, changes ACR status, or merges prose.
- Existing ARCHITECTURE rows include an embedded pipe in a change cell and
  one legacy row whose ACR link is in the change cell. The parser preserves
  those rows instead of rewriting their descriptions.

Consequences:
Parallel ACR changes can be reconciled without silently dropping a version.
The developer and reviewer still judge the architecture text and accept the
ACR under the Brain rules. No runtime or VM behavior changes.

References:
- [T-0049](../../tasks/current/T-0049-agent-skills.md)
- [ACR template](../../architecture/changes/ACR-TEMPLATE.md)

### Test state

- **RED seen:** five behavior cases failed against the naive helper: parallel
  versions lost one branch, changelog rows stayed shuffled, conflicts were
  accepted, a missing row was accepted, and a missing ACR link was accepted.
- **RED seen:** the current architecture's embedded-pipe and legacy
  three-column changelog rows were rejected; Windows CLI output failed on
  a Unicode `≤` character.
- Focused GREEN: **11 passed**. The helper also read both inputs from the
  current real `ARCHITECTURE.md` successfully. The first full run was stopped
  when main advanced. The fresh integrated-main full suite on `6a72339` passed:
  **1643 passed, 62 skipped, 1 deselected in 1250.45s**, exit 0. The sole
  deselection is the known detached-CI Brain test. Ruff, Brain lint/audit,
  skill validation and whitespace checks passed.
- S3 pre-reviewed the real current document (27 rows, version value identical),
  simulated two parallel branches and a same-version collision, and cleared
  the documentation follow-ups. References now sit outside the roll-up sections;
  the skill explains the one-time sorting of the old `1.8.5`/`1.8.4` rows.

### Next step

After this protected skill PR is reviewed and merged, continue T-0049 S3 with
`add-capability` on a separate branch and PR. S1 coordinates the shared task
status row after the parallel skill PRs merge.
