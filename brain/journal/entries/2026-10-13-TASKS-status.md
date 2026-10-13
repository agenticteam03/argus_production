## 2026-10-13 — Task files brought up to date with the merged pull requests

Type: process
Who: conantkd (+ agent)
Context: many files in `tasks/current/` still said `in progress`, `in review` or "waits for review" after their pull
requests had merged (checked against GitHub's merged list, #7-#112); two ACRs applied to the architecture still said
`proposed`.
Decision / result:
- 31 finished tasks moved to `tasks/completed/` with their final status and PR numbers (the rule in
  `tasks/completed/README.md`); every link to them rewritten (`lint` clean).
- 5 stay in `tasks/current/`: E2E-8 (planned, `juanbetancurm`), OP-004 and OP-008 (the first `--apply` waits for a
  teammate's review of the dry run), T-0016 (Playwright, the network guard and the contract check still open,
  `juanes6554`), T-0019 (its deny-floor follow-up #114 is in review). OP-004's status said "VM dry run pending": it
  was done 2026-10-10.
- T-0023 step 3 is done through E2E-1 to E2E-6 (SC-01 to SC-08 at 5/5); E2E-4's step 2 was E2E-3 step 2's SC-08 5/5.
- ACR-0003 `accepted` (`juanbetancurm`'s approval of #45, 2026-10-09) and ACR-0008 `accepted` (approval of #89,
  2026-10-12): both were already applied (architecture 1.8.3 and 1.8.7).
- The class-registry question of T-0025 and EVAL-2 is now an open decision of its own: D-003 in `OPEN_PROBLEMS.md`.
  OP-001 there: PR #44 merged.
Consequences: Brain only, no code. Done on the roll-up branch because `NEXT_STEP.md` links to some of the moved files.
References: `brain/tasks/completed/`, `brain/OPEN_PROBLEMS.md` (D-003).
