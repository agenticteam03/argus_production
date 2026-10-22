## 2026-10-22 — ACR-0029 proposed: confirmed incident feedback

Type: architecture proposal (documentation only)
Who: `juanbetancurm` (+ agent); review: `conantkd`
Context: T-0048 needs an ACR before a human feedback route or confirmed-case memory is implemented. The deferred
NEXT-PHASE area G has no section in the merged plan; the proposal follows T-0048's explicit scope. Main/base is
`9d65e1e`; ACR-0029 was free there and in the open PRs.
Decision / result:
- Proposed insert-only feedback and verification, a derived outcome view, the human-only feedback route with
  ACR-0018 gates, confirmed memory, an interpretable bounded ranking prior and offline export to reviewed drafts.
- Each feature names affected architecture sections, future implementation tests, alternatives and rollback.
  Who may label, step-up coverage, retention and verification thresholds remain acceptance decisions; prior weight
  defaults to zero and activation needs reviewed evaluation.
- Peer findings clarified that an unobserved corrected cause stays unconfirmed, an exact authorized retry needs no
  new step-up and writes nothing, and exported incidents never enter OP-013's independent held-out set. Corrected
  an exact architecture quotation and used the established journal shape. Re-review clear (S3).
Consequences: status remains `proposed`; no architecture application/version bump, code, contract, migration,
export artifact or VM action. Only the ACR, T-0048 metadata and this journal entry change. Acceptance and the
required ACR-0018 access/audit deployment gates precede implementation.
References: [T-0048](../../tasks/current/T-0048-incident-feedback.md),
[ACR-0029](../../architecture/changes/ACR-0029-incident-feedback.md).

### Test state

Documentation only: no new runtime behavior and no runtime RED/GREEN claim. Implementation tests are a plan in
ACR-0029 §4.1. Full offline regression on main `9d65e1e` plus this proposal: **1471 passed, 62 skipped, 1 deselected**,
exit 0 (886.92 s); only the known detached-CI Brain test was deselected. The process used Git for Windows' Bash and
a fixture Git-discovery ceiling; no global configuration or additional exclusion changed. Peer fixes are wording
only; final Brain/link/whitespace checks after them are clean. Ruff (`argus services ops`) and Brain lint/audit are
clean; 11 relative links resolve, all 22 cited architecture subsections exist and the documentation uses LF.

### Next step

Peer re-review and final document checks are complete. Publish the protected proposal PR through a developer-run
block requesting `conantkd`. Resolve acceptance questions before implementation. Apply the architecture with the
first code in a later reviewed PR; release no route or ranking prior from this proposal.
