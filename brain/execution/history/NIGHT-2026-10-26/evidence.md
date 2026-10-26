# NIGHT-2026-10-26 — evidence: applying the digest schedule and four live checks (2026-10-26 UTC, conantkd)

Run by conantkd's agent over ssh at conantkd's request, both leases (session `13d7ed00`). A.1 changed vm-095's checkout
and restarted the scheduler; every other row was read-only. Commands: [`code.bash`](code.bash) (A.1; the read-only
queries ran inline in the agent container). Sanitized: no name, address, bucket or key.

| Check | Observed | Result |
|---|---|---|
| Incidents of 2026-10-22 to 2026-10-24 with no run since 2026-10-21 (raised during the night) | each has 11 run events; all three are manual `check` requests (`evidence_pack`, no investigation, no model call), `undiagnosable` because their targets had no fresh samples (two are `vm-095/container:argus-lab-worker`, SC-02's crash-loop container, idle outside its scenario). No model call since 2026-10-21 19:33Z: there was no alert to investigate | no fault |
| A.1 apply #338 | `DEPLOY OK: b6e64ebaf58e (b6e64eb)`; scheduler `running restarts=0`; log: `audit digest: every 86400 s`, `audit chain: security.audit_chain_verified: 312 chained, 0 problem(s)`, `audit digest: shipped 0 digest(s), 0 conflict(s)` (every closed day already shipped); real error lines 0; `ref=b6e64eb`, `LAB BASELINE OK` | OK |
| Phase 17 exit proof, live | SC-03's incident `inc_1b392a41406e` (recalled RB-003, RB-009), the API's `next_actions` evaluated at the incident's time: **`container.start` on `argus-lab-cache` only**; no restart of `argus-lab-api`. Evaluated now, the list is empty: the status observation is no longer fresh, as designed | PASS |
| Phase 16, public 404, live | no route exists under `/api/v1/ops/` yet (privileged routes arrive in phase 19); on the public edge `/api/v1/ops/` and `/api/v1/ops/anything` answer **404**; `/api/v1/me` answers 401 | PASS |
| Baseline evaluation on main (offline, no model) | 72 cases: 68 passed (0.96), hard checks 0 0 0 0; the four failing cases are the same as in T-0046 L6 step 02's run; the six cases of #333 all pass; no case changed result | no regression |
