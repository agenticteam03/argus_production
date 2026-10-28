# ACR-0036 — Stalled worker incident class

| Field | Value |
|---|---|
| Status | `accepted` |
| Proposed by | `conantkd` (+ Codex) · 2026-10-27 |
| Accepted by | `conantkd` · 2026-10-27 (confirmed in the review session for PR #366) |
| Second approval (safety principle only) | not required |
| Architecture version | proposed: `1.8.40` → `1.8.41` |
| Task / PR | TASK-54 · PR #366 |

## 1. Detect and explain

The SC-10 job worker can remain alive while it stops processing a growing Redis queue. PR #366 adds the `worker_stalled` detector, its signals, the baseline evidence plan, the alert, and RB-022. The initial pull request added this class to the architecture class table without an ACR, a version bump, or a changelog row; this record closes that gap.

## 2. Why the current architecture is insufficient

The class table in `ARCHITECTURE.md` §1.3 maps each incident class to runbooks and a strategy. It has no row for a worker that is alive but not processing queued jobs. Existing `container_restart_loop` and `health_check_failed` rows do not describe this symptom. The same section still describes the library as RB-001 through RB-021, although this change adds RB-022.

## 3. Smallest reasonable change

Add one row to the §1.3 class table: `stability | worker_stalled | RB-022 | RB-003, RB-004 | baseline`, and extend the library range to RB-022. Keep the write gate closed and all diagnosis reads narrow and audited. The detector treats absent or non-finite signals as unknown; it attributes a dependency cause only from observed status or a recorded broken link.

**Alternatives considered:**

- Reuse `health_check_failed`: rejected because the worker's health endpoint can answer while job progress stops.
- Leave the architecture table unchanged and register the class only in code: rejected because the authoritative mapping would be incomplete.

## 4. Consequences

- Code and tests: the class registry, detector, baseline strategy, signals, alert, UI signal list, inventory, runbook, and their tests in PR #366.
- Deployment: Prometheus on vm-166 joins the lab application network to scrape the worker; vm-095's Prometheus does not join it. Live behavior remains unverified until deployment.
- Risk: a missing, stale, or non-finite worker metric could be mistaken for health; the detector reports it as unknown.
- Reversal: remove the class, its signal and alert wiring, and the table row in a reviewed change.
- Safety principle changed: no. The existing read-only and host-isolation rules remain in force.

## 5. Decision

`conantkd` accepted the class mapping and the RB-022 library update on 2026-10-27 during the PR #366 review session. No safety principle changes.

## 6. Applied

- [x] `ARCHITECTURE.md` updated, version bumped to 1.8.41, changelog line added with this ACR's link
- [x] journal entry
- [x] the ACR, the architecture change and the first code that needs it are in the same pull request
