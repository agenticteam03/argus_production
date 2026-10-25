# NEXT-PHASE — From diagnosis to supervised remediation (proposal)

| Field | Value |
|---|---|
| Status | `approved` as a plan (PR #170 merged); ACR-0020 accepted for offline 21A, safety approval pending |
| Phase | 15–23 (planned, [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | [ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md) operator access and audit · [ACR-0019](../../architecture/changes/ACR-0019-human-approved-remediation.md) human-approved remediation · [ACR-0020](../../architecture/changes/ACR-0020-operator-terminal.md) operator terminal (`accepted`, 21A) · [ACR-0022](../../architecture/changes/ACR-0022-autonomous-investigation.md) more autonomous investigation |
| Sources | this proposal (juanbetancurm) merged with `conantkd`'s "Argus actúa" (2026-10-18) |
| Branch | `task/NEXT-PHASE-proposal` (documentation only) |
| Owner | `juanbetancurm` and `conantkd` (+ agents); lanes below |
| Needs the VM lease | no (documentation only) |

## Goal

Move Argus from read-only diagnosis to **supervised remediation**, with a human operator as the final approver of
every change:

1. **Argus-proposed fix (ACR-0019):**
   - Argus proposes **one action from a closed catalogue**, allowed by the target's **service card** and the
     **action card**, with cited evidence and grounds (a runbook, the memory of verified actions, or curated vendor
     documentation), a **prediction** and alternatives;
   - a **judge** model reviews it and can only make it stricter;
   - an authenticated human approves that frozen proposal, with a fresh second factor;
   - the **worker** executes exactly that action through an exact-route gateway;
   - Prometheus confirms the recovery and the prediction, and the result goes into the memory of actions.
2. **Operator terminal (ACR-0020):** the operator in charge fixes the problem in a full, recorded terminal in the UI,
   under their own identity. "Insert" offers only commands the cards allow; the shell itself is unrestricted for the
   authorized operator.
3. **More autonomous investigation (ACR-0022):** reads and suggestions only.
   - open investigations for incidents no class covers;
   - automatic follow-up checks after any fix;
   - new reads ("what changed recently", allowlisted config files, vendor documentation);
   - isolated internet research that only produces suggestions for the operator.

All of it rests on **ACR-0018**:
- one account per person, WebAuthn MFA, step-up, revocable sessions, explicit permissions;
- a tamper-evident audit copied off Host A;
- privileged routes only on a private path.

## What each proposal contributed

| From this proposal | From `conantkd`'s "Argus actúa" |
|---|---|
| MFA, step-up, sessions, permissions, audit chain, private path (ACR-0018) | the closed catalogue organized by intent; "the model never writes commands" |
| the operator terminal (ACR-0020) | service cards and action cards with code-evaluated preconditions |
| the responsibility model; why approval and live gauges are not enough | grounds and a computed basis; a model-only basis becomes a suggestion |
| leases as automatic holds; lab-only scope; per-pair release | risk colours in a reviewed table; colour only goes up |
| the prompt-injection escape (#166) and the self-merge protected paths | the mandatory prediction and alternatives; verification of the prediction |
| | the judge (stricter only, fail closed) |
| | the memory of verified actions; runbook drafts from repeated verified fixes |
| | `suggest_action`; isolated research for suggestions; the curated reference corpus |
| | scenarios with answer keys (correct / acceptable / useless / harmful) and traps |
| | the worker dispatches (with the controls of ACR-0019 §3.9) |

**Deferred (each needs its own ACR later):**
- earned autonomy (pre-approvals, veto windows); shadow mode measures it from now on;
- more action families: PostgreSQL, configuration with a hash lock, rollback, Linux host actions, Ansible and other
  generated tools;
- other container runtimes.

## Responsibility model (ACR-0019 §3.1)

- The approving operator is accountable for the decision to execute a specific, frozen proposal.
- The team is accountable for which actions Argus may propose (the catalogue, cards and risk table, reviewed in PRs),
  for what the approver is shown, and for ensuring that only the approved action runs, once, verified and recorded.
- Human approval is required but never sufficient.
- In the terminal, the operator is directly responsible for the commands they type; the controls there are access and
  recording.

## Why approval and live gauges are not enough

| Risk | Example in this project | Control (ACR) |
|---|---|---|
| The data supports the wrong action | SC-03: the victim `argus-lab-api` looks broken; restarting it is wrong (RB-003) | service card `never`, action card `not_useful_when`, the "never offered" list, the judge (0019) |
| Same name on two hosts | `argus-lab-worker` on vm-095 and vm-166 | proposal bound to host + container id; per-host gateway (0019) |
| Approval and execution at different times | the container recreated, the incident resolved, a teammate's scenario started | identity binding, expiry, precheck with the cards' preconditions, leases as holds (0019) |
| What runs differs from what was shown | a log line escaping its data block (#166) | the dispatch reads only frozen rows; import boundary; exact-route gateway; socket proxy (0019) |
| "Live" data has gaps | cached views, stale metrics, `unknown` links | unknown never ok; verification and the prediction on fresh samples (0019) |
| A stolen account or session | a password alone approves | WebAuthn, step-up per approval, private path, sessions (0018) |
| Approval fatigue | an alert storm | small released set, colours, typing the name for red, rate limits, emergency stop (0019) |
| Partial failure and our own bugs | a crash mid-dispatch | ledger, reconciliation, never a blind retry (0019, §14) |
| Accountability without proof | an edited audit row | hash chain + off-host digest (0018) |

## Plan

| Phase | Content | Lane | ACR | Lease | Exit proof |
|---|---|---|---|---|---|
| **15. Foundations** | fix OP-015 and OP-016; extend `SELF_MERGE_PROTECTED` (`config/actions/`, `config/risk.yaml`, the dispatch module, the gateway); OP-014 steps 4–8 in CI | Quality | — | no | the gates green on CI |
| **16. Operator access and audit** | ACR-0018 | Integration + Quality + Frontend | 0018 | deploy (both) | authorization matrix green; public 404 for privileged routes; tamper test |
| **17. Cards, catalogue and suggestions** | service cards in the inventory; action cards and the precondition interpreter; `config/risk.yaml`; the runbook `actions` block; `suggest_action`; `next_actions` in incidents (read-only); scenario answer keys and traps in the evaluation | Quality + Frontend | 0019 | deploy (both) | SC-03 suggests "start the cache" and never "restart argus-lab-api"; evaluation grades actions; no `eval` in the interpreter |
| **18. The §14 machinery, fake gateway** | tables, `ProposeRemediation` with grounds / prediction / alternatives, basis computation and downgrade, the judge, `propose_action` → `judge_proposal` → `request_approval` → `await_approval` → `precheck_action` → `execute_write` → `verify`; failure-injection and binding suites; shadow-mode recording; the write gate stays closed | Quality | 0019 | no | §14.4 and §22.2 suites green; judge fail-closed; standing test green |
| **19. Approvals in the UI and the gateway** | approvals (private path, step-up, colours, judge, typing the name for red), holds, emergency stop, suggestions, the incident's Actions tab; the action gateway + socket proxy (not yet routed); the import-boundary and token-isolation tests | Integration + Frontend | 0019 | deploy (both) | the dispatch module cannot import the LLM adapter; the tools child cannot read the action token; gateway route tests on real images |
| **20. First released pair (lab)** | `container.start` on `vm-166/container:argus-lab-cache` (SC-03), its own release PR, two reviewers | Integration + Quality | 0019 | release (both) | 5/5 scenario runs: right proposal, judge agrees, approved, executed once, prediction met, `recovered_verified`; rollback rehearsed |
| **21. Operator terminal** (may overlap 18–20 after 16) | ACR-0020: broker, SSH CA, per-person accounts, recording off-host, private path, incident linking, card-limited "Insert" | Integration + Frontend | 0020 | deploy (both) | ACR-0020 §4 tests; a drill of the terminal's incident response |
| **22. More autonomous investigation** (after 16) | ACR-0022: follow-up checks, the new reads, the curated reference corpus, the open investigation (lab scope) | Quality + Integration | 0022 | deploy (both) | follow-up checks recorded after a manual fix and after an action; an open investigation never proposes; new reads pass their inspection policy |
| **23. Isolated research** (last, disabled by default) | the research container, proxy, quarantined reader, suggestion card buttons | Integration | 0022 | deploy (vm-095) | queries carry no host/address/secret; no route to Argus's database; results never in a model request or a ground |

**Critical path:** 15 → 16 → 17 → 18 → 19 → 20. Phases 21 and 22 run in parallel once 16 is deployed; 23 comes last.

**Later, with their own ACRs:**
- more action families: `db-action` for PostgreSQL, `config.patch` / `config.restore` with a hash lock,
  `deployment.rollback`, Linux `host-action`, Ansible / OpenAPI / pattern-generated tools;
- other container runtimes;
- **earned autonomy**, using the shadow-mode data from phase 18 on.

The UI backend (T-0045, ACR-0021), observed topology with scheduled edge checks, and explicit hypotheses with cause
ranking are separate tracks: the live dependency graph is [T-0046](T-0046-live-dependency-graph.md)
([ACR-0025](../../architecture/changes/ACR-0025-live-dependency-graph.md)), hypotheses and the cause ranking are
[T-0047](T-0047-hypotheses-cause-ranking.md) ([ACR-0024](../../architecture/changes/ACR-0024-hypotheses-and-cause-ranking.md)),
memory and feedback are [T-0048](T-0048-incident-feedback.md); controlled external knowledge is ACR-0022 §3.4–3.5.

## Cross-cutting gates

| Gate | Where | Blocks |
|---|---|---|
| Unit, contract, Postgres and Docker tests (gateway, socket proxy, broker isolation, token isolation, import boundary) | CI on every pull request | any merge |
| Authorization matrix, step-up, revocation, audit chain | CI | phases 19–21 |
| §14.4 failure injection, §22.2 binding tests, judge fail-closed, basis downgrade, colour only goes up | CI | phase 20 |
| Evaluation: answer keys; hard checks (`unauthorized_actions`, `actions_on_forbidden_targets`, `action_without_valid_approval`, `harmful_actions` and the existing three) at 0; accuracy not below the previous run | scheduled evaluation + before each release PR | phase 20 |
| Prompt-injection regression (logs, files, history, fetched pages) | CI | phases 17–23 |
| Scenario runs 5/5, `nonint-check.sh` clean | `code.bash`, leases | each deployment and release |
| Two reviewers | the PR | every `write_gate.open` change, every card or risk-table change that adds power, terminal enablement, research enablement |

## Open decisions (for the proposal review)

1. Terminal broker: **decided by ACR-0020 (2026-10-23): build the narrow Argus broker** so it reuses ACR-0018's
   identity, step-up and private path and binds each session to its incident and lease. Teleport Community Edition
   remains the scale-out alternative, but adds another identity/UI plane and a licensing decision. The independent
   safety approval is still pending.
2. Private path: a team VPN, or mTLS client certificates with an address allowlist? (`wg0` belongs to the protected
   deployment and is not reused without its owner's agreement.) **Answered (ACR-0018 §5):** mTLS with an address
   allowlist on the existing edge.
3. Who holds `approve_action` and `open_terminal:<host>`; is separation of duties enforced on the lab profile?
   **Answered (ACR-0018 §5):** `approve_action` for the three enabled operators; `open_terminal:<host>` for nobody
   until ACR-0020 decides it; on the lab profile a self-approval is allowed and recorded, not refused.
4. First released pair: `container.start` (this proposal) or `container.restart` (`conantkd`'s 1A) on
   `argus-lab-cache`? The cache is stopped in SC-03, so `start` is the narrower action. **Answered (ACR-0019 §5):**
   `container.start`.
5. The judge's model: another provider or family than the deciding model, and its cost. **Set when phase 18
   starts (ACR-0019 §5)**, from a measured comparison.
6. Approval expiry (proposed 30 min in the lab) and the per-target action rate (one per 10 min). **Answered
   (ACR-0019 §5):** 30 minutes; one per 10 minutes.
7. The off-host store for the audit digest and the terminal recordings, and their retention. **Answered (ACR-0018
   §5):** an object-storage bucket with a locked retention rule (no versioning) and a put-only credential; digests 1 year,
   recordings 90 days; the provider is OCI Object Storage, administered by `conantkd`. OCI cannot combine versioning
   with a retention rule, so the bucket uses a locked retention rule without versioning (ACR-0018 §5).
8. Whether vm-095 (Argus's own host) ever gets actions (recommendation: no). **Answered (ACR-0019 §5):** no.
9. Whether drills count as memory for production (recommendation: counts are per scope; lab counts never apply to
   production). **Answered (ACR-0019 §5):** counted per origin.
10. The model-evaluation budget for phases 17, 18 and 20. **Set in each phase's plan (ACR-0019 §5).**

## Not in this proposal

No code, test, configuration or deployment change. `ARCHITECTURE.md`, `policies/SECURITY.md` and
`policies/NETWORK.md` change only when each ACR is applied, with its first code (ACR template, "Applied").
