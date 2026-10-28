## 2026-10-28 - The judge sees the dependency's read and what was ruled out

Type: fix
Who: conantkd (+ agent)
Context: in the second S4 rehearsal (main `f3218e0`) the judge answered `doubt` on restarting the stalled worker
(`inc_50ca7af5bee4`). Two of its reasons were about what it could not see: "Database status ... unavailable, leaving a
dependency cause unresolved" and, implicitly, why nothing else was the cause. The diagnosis is by elimination (the
worker is running, its declared dependency is running, no link is broken), but the proposal cited only the worker's
status, the alert and the metric snapshot. The cache's `container.status`, which shows the dependency running, was read
and stored yet never cited, and the judge sees only what a proposal cites. Nothing in the proposal said what had been
excluded. (The metric snapshot is 431 characters, inside the judge's 480, so its rate, queue and age were visible.)
Decision / result:
- `argus/actions/incident.py`: a candidate also cites the newest successful `container.status` of each declared
  dependency of its cause (after the cause's own status and the incident target's symptom, snapshot and links).
- `argus/infrastructure/action_wiring.py`: the proposal's rationale ends with what the cited reads exclude, built from
  data and no model text: "no OOM kill" only when `oom_killed` is false, "0 restarts" only when the count is zero, and
  "dependency X is running" only for a cited dependency read as running. When nothing is excluded it says nothing.
Consequences: the judge and the approver read the same sentence. This changes what is shown, not the judge's
instructions or criteria; reading the worker's logs, the verification plan in the packet and the judge's rubric stay
out and need their own ACR (amendment to ACR-0019 section 3.8) and a measured comparison.
References: [demo plan](../../tasks/current/DEMO-argus-acts.md), ACR-0019 section 3.8, RB-022.

### Test state

Three tests, each red without the change: a candidate cites only the newest successful dependency read (not an older,
a failed or an unrelated one), the rationale names the exclusions, and a fact is claimed only when it holds. The
phase 18, 19 and 20 files, the UI contract and the evaluation files pass locally; ruff is clean. CI is the full check.

### Next step

Merge, redeploy vm-095's worker and repeat S4 five times to see how often the judge agrees.
