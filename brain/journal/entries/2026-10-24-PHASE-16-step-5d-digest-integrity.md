## 2026-10-24 — PHASE-16 step 5d: verify the audit chain before checking digests

Type: code (offline)
Who: juanbetancurm (+ agent)
Context: review of #314 found that `check_digest_files` compared signed digests to stored row hashes without
checking that the current audit row bodies still match those hashes.
Decision / result:
- `check_digest_files` now verifies the supplied rows with `audit_chain.verify` and reports its generic row-level
  problems alongside the signed digest and series checks.
- A regression changes a row body while keeping its stored hash. `audit_chain.verify` detects the mismatch; before
  the fix, `check_digest_files` accepted the otherwise valid digest series.
Consequences: the manual check detects an edited audit row before trusting a digest series. No deployment change;
the digest schedule remains disabled.
References: [ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md) §5, §6;
[PHASE-16](../../tasks/current/PHASE-16-operator-access.md).

### Test state

Red seen: the new regression failed because `check_digest_files` returned no problems for the tampered row. Green:
the related audit-chain and digest tests passed (59 passed, 2 skipped). The first full-suite attempt placed pytest's
temporary tree inside the worktree, so deployment tests saw the parent Git checkout and failed. With the temporary
tree outside the worktree, the final full offline suite passed: 1876 passed, 74 skipped, 1 deselected (15m 38s).

### Next step

S4 prepares the commit/push/PR block for the stacked fix; no deployment change is included.
