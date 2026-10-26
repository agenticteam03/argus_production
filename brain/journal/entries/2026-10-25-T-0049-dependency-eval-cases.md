## 2026-10-25 — T-0049 dependency evaluation cases

Type: offline evaluation fixtures
Who: juanbetancurm (+ agent)
Context: The dependency_unavailable evaluation set had five cases, too few to support the next H4 gate. This task adds six
cases while leaving class offers, production behavior and existing labels unchanged.
Decision / result:
- Added three diagnosed cases: an OOM-killed cache, a stopped database and a database isolated from the client network.
- Added three escalation cases: a DNS-vantage failure, cache authentication failure and intermittent backend timeouts.
- Added status, stats, health, events, connectivity and network-probe fixtures for the affected containers.
- The OOM case records exit 137, the OOM flag, memory at the limit, and `oom`/`die` events.
- Tests cover the six case IDs, targets, labels, dependency states, network evidence and OOM evidence. The baseline replay
  is covered by the shared D-003 evaluation test.
Consequences: The fixture set now has three diagnosed and three ambiguous cases for `dependency_unavailable`. The cases
are offline fixtures; no class strategy or model behavior was changed. The OOM expected-hypothesis label also includes the
free-text `memory_exhaustion` cause.

### Test state

- Full offline suite on the PR head: 1919 passed, 74 skipped, 1 deselected; exit 0.
- After merging `origin/main` at `7f8c14b`, the focused TASK-19, T-0047 and evaluation tests passed: 117 passed.
- Ruff, Brain lint/audit and `git diff --check` are clean. Brain `split_entry` validation is run for this entry.

### Next step

Claude_1 prepares the developer-run update block for PR #333. Conantkd reviews the updated PR head. No VM action or model
call is needed.