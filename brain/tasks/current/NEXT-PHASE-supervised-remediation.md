# NEXT-PHASE — From diagnosis to supervised remediation (proposal)

| Field | Value |
|---|---|
| Status | `proposed` — team review of the proposal PR; no implementation starts before it is approved |
| Phase | 15–21 (planned, [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | [ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md) operator access and audit · [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md) human-approved remediation · [ACR-0020](../../architecture/changes/ACR-0020-operator-terminal.md) operator terminal — all `proposed` |
| Branch | `task/NEXT-PHASE-proposal` (documentation only) |
| Owner | `juanbetancurm` (+ agent); lanes below |
| Needs the VM lease | no (documentation only) |

## Goal

Move Argus from read-only diagnosis to **supervised remediation**, with the operator in control of every change:

1. **Argus-proposed fix (ACR-0019):** Argus proposes one action from a runbook's action menu; an authenticated
   approver approves that frozen proposal with a fresh second factor; a restricted executor that never sees model
   output runs exactly that action; Argus verifies recovery on fresh evidence.
2. **Operator terminal (ACR-0020):** the operator in charge fixes the problem manually in a full, recorded terminal
   in the UI, under their own identity.

Both rest on **ACR-0018**: one account per person, WebAuthn MFA, step-up, revocable sessions, explicit permissions,
a tamper-evident audit copied off Host A, privileged routes only on a private path.

## Responsibility model (ACR-0019 §3)

The approving operator is accountable for the decision to execute a specific, frozen proposal. The team is
accountable for which actions Argus may propose, for the accuracy and completeness of what the approver is shown,
and for ensuring that only the approved action runs, on the approved target, at most once, with its outcome verified
and recorded. Human approval is required but never sufficient. In the terminal, the operator is directly responsible
for the commands they type; the controls there are access and recording.

## Why approval and live gauges are not enough

| Risk | Example in this project | Control (ACR) |
|---|---|---|
| The data supports the wrong action | SC-03: the victim `argus-lab-api` looks broken; restarting it is wrong (RB-003) | runbook action menus, `never` rules in code (0019) |
| Same name on two hosts | `argus-lab-worker` on vm-095 and vm-166 | proposal bound to host + container id; per-host gateway (0019) |
| Approval and execution at different times | the container recreated, the incident resolved, a teammate's scenario started | identity binding, expiry, precheck, leases as holds (0019) |
| What runs differs from what was shown | a log line escaping its data block (#166) | an executor without model access; exact-route gateway; socket proxy (0019) |
| "Live" data has gaps | cached views, stale metrics, `unknown` edges | unknown never ok; verification on fresh samples (0019) |
| A stolen account or session | a password alone approves | WebAuthn, step-up per approval, private path, sessions (0018) |
| Approval fatigue | an alert storm | small released set, rate limits, emergency stop (0019) |
| Partial failure and our own bugs | a crash mid-dispatch | ledger, reconciliation, never a blind retry (0019, §14) |
| Accountability without proof | an edited audit row | hash chain + off-host digest (0018) |

## Plan

| Phase | Content | Lane | ACR | Lease | Exit proof |
|---|---|---|---|---|---|
| **15. Foundations** | fix OP-015 (§14 described as built) and OP-016 (shared password); extend `SELF_MERGE_PROTECTED` with the new safety paths; OP-014 steps 4–8 in CI (coverage on changed lines, SAST, dependency audit, workflow lint, scheduled model evaluation) | Quality | — | no | the gates green on CI |
| **16. Operator access and audit** | ACR-0018: per-person accounts, WebAuthn, step-up, sessions and revocation, persistent limiter, EdDSA keys, permissions with host scopes, audit hash chain + off-host digest, the private path | Integration + Quality + Frontend | 0018 | deploy (both) | authorization matrix green; public 404 for privileged routes; tamper test |
| **17. Suggestions** | the runbook **Actions** section; `next_actions` in incidents; the UI "Next steps" card with "Copy" (read-only) | Quality + Frontend | 0019 (§12.2 part) | deploy (both) | SC-03 suggests "start the cache" and never "restart argus-lab-api"; evaluation `expected_action` / `forbidden_actions` |
| **18. The §14 machinery, fake gateway** | tables, graph nodes, write contract, failure-injection and binding suites; the write gate stays closed | Quality | 0019 | no | §14.4 and §22.2 suites green; standing test green |
| **19. Approvals and the executor** | approvals UI (private path, step-up), holds, emergency stop; `argus-actor`; the action gateway + socket proxy (not yet routed) | Integration + Frontend | 0019 | deploy (both) | the worker cannot reach a gateway; the actor refuses unapproved rows; gateway route tests on real images |
| **20. First released pair (lab)** | `container.start` on `vm-166/container:argus-lab-cache` (SC-03), its own release PR, two reviewers | Integration + Quality | 0019 | release (both) | 5/5 scenario runs: right proposal, approved, executed once, verified healthy; rollback rehearsed |
| **21. Operator terminal** (may overlap 18–20 after 16) | ACR-0020: broker, SSH CA, per-person accounts, recording off-host, private path, incident linking, "Insert" | Integration + Frontend | 0020 | deploy (both) | ACR-0020 §4 tests; a drill of the terminal's incident response |

**Critical path:** 15 → 16 → 18 → 19 → 20. Phase 17 and 21 run in parallel once 16 is deployed.

**Later phases, each with its own ACR when proposed** (from the next-phase notes, not part of this proposal):
observed topology with live dependency checks; explicit hypotheses and transparent cause ranking; incident feedback
and outcomes (was the diagnosis right, what fixed it); controlled external knowledge from approved sources only.
Incident feedback is the natural next ACR: phase 20's verification and phase 21's sessions produce the outcomes it
records.

## Cross-cutting gates

| Gate | Where | Blocks |
|---|---|---|
| Unit, contract, Postgres and Docker tests (including gateway, socket proxy and broker isolation) | CI on every pull request | any merge |
| Authorization matrix, step-up, revocation, audit chain | CI | phases 19–21 |
| §14.4 failure injection, §22.2 binding tests | CI | phase 20 |
| Evaluation hard checks (`unauthorized_actions`, `actions_on_forbidden_targets`, `action_without_valid_approval` and the existing three) at 0; accuracy not below the previous run | scheduled evaluation + before each release PR | phase 20 |
| Prompt-injection regression (logs, files, history) | CI | phases 17–20 |
| Scenario runs 5/5, `nonint-check.sh` clean | `code.bash`, leases | each deployment and release |
| Two reviewers | the PR | every `write_gate.open` change, terminal enablement |

## Open decisions (for the proposal review)

1. Terminal broker: adopt (Teleport Community Edition) or build (OD-17)?
2. Private path: a team VPN, or mTLS client certificates with an address allowlist? (`wg0` belongs to the protected
   deployment and is not reused without its owner's agreement.)
3. Who holds `approve_action` and `open_terminal:<host>`; is separation of duties enforced on the lab profile?
4. First released pairs: `container.start argus-lab-cache` only, or also `container.restart` for SC-02's worker?
5. The off-host store for the audit digest and the terminal recordings, and their retention.
6. Approval expiry (proposed 15 min) and the per-target action rate (proposed one per 10 min).
7. The model-evaluation budget for phases 17 and 20 (trials per change).

## Not in this proposal

No code, test, configuration or deployment change. `ARCHITECTURE.md`, `policies/SECURITY.md` and
`policies/NETWORK.md` change only when each ACR is applied, with its first code (ACR template, "Applied").
