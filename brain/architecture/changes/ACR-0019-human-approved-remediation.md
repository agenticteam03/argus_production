# ACR-0019 — Human-approved remediation: Argus proposes, an operator approves, a restricted executor acts

Part of the next-phase proposal ([task](../../tasks/current/NEXT-PHASE-supervised-remediation.md)). Depends on
[ACR-0018](ACR-0018-operator-access-and-audit.md) (operator access and audit), which must be applied and deployed
first.

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | juanbetancurm (+ agent) · 2026-10-18 |
| Accepted by | pending (team review of the NEXT-PHASE proposal PR) |
| Second approval (safety principle only) | **required**: read-only and the write gate (the first released write capability), least privilege (a new executor and gateway), secrets (action-gateway tokens) |
| Architecture version | the next free version when applied (after ACR-0018) |
| Task / PR | NEXT-PHASE · PR (this proposal) |

## 1. Detect and explain

Argus diagnoses and recommends; a human then repairs by hand, outside Argus, with no link back to the incident. The
team wants the next step: an operator can **approve a fix that Argus proposes**, and Argus executes exactly that fix
and verifies recovery.

ARCHITECTURE already designs this path (§4.5 action gateway, §13.3 write gate, §14 approval → resume → precheck →
ledger → reconcile → verify, §14.8 the write contract, §22.2 release criteria), but:

- **none of it is implemented** (no `action_proposal` / `approval` / `action` / `target_hold` tables, no write
  contract, no approval routes), although §14 says "the machinery, its tables and its tests exist from the start"
  and `IMPLEMENTATION_PLAN.md` phase 9 lists "HITL against a fake action endpoint" (OP-015);
- the design gives the action credential to **the worker** (§4.5 "the worker holds no action credential" until a
  release; §17.2 "Worker write identity | `local_write.py`"), the same process that reads model output;
- proposals are not tied to the runbooks' constraints, so a proposal can be technically valid and still wrong
  (restarting the victim, RB-002; restarting the dependent service, RB-003).

## 2. Why the current architecture is insufficient

Human approval protects the *decision*, not its inputs or its execution. The live gauges in the UI show symptoms,
not causes or targets. Cases the current design does not close:

1. **The data supports the wrong action:** in SC-03 the victim (`argus-lab-api`) looks broken on every graph; a
   proposal to restart it would look justified.
2. **Same name, two hosts:** `argus-lab-worker` exists on vm-095 and vm-166; "restart argus-lab-worker" is ambiguous
   to a reader.
3. **Approval and execution happen at different times:** the target can be replaced, the incident resolved, or a
   teammate's scenario started in between.
4. **What runs can differ from what was shown,** if the execution path can be influenced by model output (a log line
   that escaped its data block was found and fixed in #166).
5. **"Live" data has gaps:** cached views (20–30 s), stale metrics, `unknown` edges.
6. **Partial failure and our own bugs:** a crash during dispatch, a retry, a wrong route.

## 3. Smallest reasonable change

**Responsibility model** — new paragraph in §1.4, after rule 9:

> The approving operator is accountable for the decision to execute a specific, frozen proposal. The team is
> accountable for which actions Argus may propose, for the accuracy and completeness of what the approver is shown,
> and for ensuring that only the approved action runs, on the approved target, at most once, with its outcome
> verified and recorded. Human approval is required but never sufficient: every action also passes the controls of
> §13–§14.

**§1.2**, before: "In this release **no write capability is released**: Argus is read-only, and remediation is
performed by humans." After: "Write capabilities are released one `(capability, target)` pair at a time (§13.3,
§22.2), on lab targets only in this release; every execution needs a human approval of a frozen proposal (§14)."

**§4.5 and §17.2 — the executor never sees the model.** A new container **`argus-actor`** replaces "the worker's write
path":
- it claims only `action` rows whose approval is `approved` and whose precheck passed;
- it holds the per-host action-gateway token; it has **no model client and parses no model output**;
- the worker writes proposal rows only and has no network route to any action gateway (a tested property).

§17.2 row before: "Worker write identity | `local_write.py` | action-gateway credential per host (after a release
only)". After: "Actor identity | `argus-actor` | action-gateway credential per host (after a release only)".

**§4.5 — the action gateway** gains a Docker **socket proxy** with path ACLs between it and the socket, so a bug in
the gateway still cannot reach another Docker API. Routes are rendered from a reviewed `config/actions.yaml` (exact
route + exact targets per released pair).

**§12.2 / §14.8 — proposals come from runbook menus.** A class's runbooks declare their actions in a machine-readable
**Actions** section (`action_id`, `capability`, typed placeholders, `preconditions`, `never` rules, verification
signals, `reversible`, `risk`). A proposal names an `action_id` and fills only its placeholders from the incident; a
free-form proposal is refused by the harness. `never` rules are evaluated by code at proposal and at precheck.

**§14.4 step 7 (precheck)** additions: no other developer's active VM lease on the target's host (an active lease is
an automatic hold); no other action on the same target within 10 minutes; the incident class still detected on a
fresh sample.

**§14.3 — approving in the UI:** the approval view shows the frozen proposal: capability, host-qualified target and
its identity (container id), arguments, the runbook action and its constraints, the evidence ids with their source
and time, the precheck preview, reversible yes/no, the expiry (15 minutes). Answering needs the `approve_action`
permission, a human principal, the private path and a step-up token bound to `approval_id + proposal_digest`
(ACR-0018). An approver-only **emergency stop** places a global hold.

**§13.3 / §22 — release scope for this phase:** `write_gate.open` may list only `argus-lab-*` targets. Candidate
first pairs (each released by its own reviewed PR, two reviewers, §22.2 criteria, 5/5 scenario runs):
`container.start` on `vm-166/container:argus-lab-cache` (SC-03); possibly `container.restart` on
`vm-095/container:argus-lab-worker` for the non-OOM crash (SC-02, RB-008). Argus's own containers, Prometheus, the
gateways, the probes and the protected objects are never action targets.

**§15.1 — verification:** unchanged in principle (fresh samples only); its result is recorded per incident.

**§21.2 — evaluation:** new labels (`expected_action`, `forbidden_actions`) and hard checks at 0:
`unauthorized_actions`, `actions_on_forbidden_targets`, `action_without_valid_approval`.

**Alternatives considered:**
- A: **keep Argus read-only; humans repair outside Argus.** Safe, but the incident loses the link to its fix, and
  remediation stays slow; ACR-0020 (the terminal) covers manual repair, this ACR covers routine ones.
- B: **implement §14 as written (the worker holds the action credential).** Rejected: the process that parses model
  output would hold write authority; one injection or parser bug is a write.
- C: **let the model write the command, the operator approves the text.** Rejected: the text shown and the command
  run can diverge; approvals of free text do not scale to safe execution.
- D: **auto-approve low-risk actions.** Rejected by §1.4 rule 2 (no write without an authenticated human's approval).

## 4. Consequences

- **Code:** migrations for §14.1's tables; graph nodes `propose_action`, `request_approval`, `await_approval`
  (LangGraph `interrupt`), `precheck_action`, dispatch, `verify`; `capabilities/write_contract.py`; the runbook
  Actions parser and the proposal validator; `argus-actor`; the action gateway and socket proxy; approval and hold
  routes; UI approval page.
- **Tests (before any release):** the §14.4 failure-injection suite; the §22.2 binding tests (changed arguments,
  replaced target, resolved incident, expired proposal, changed inventory, active hold, reused token, non-human or
  unscoped approver, other developer's lease); the actor refuses a row without a valid approval or a passed precheck;
  the worker cannot reach a gateway; gateway exact-route and socket-proxy tests on the real images; reconciliation and
  `indeterminate` → escalate, never retry; the standing write-gate test stays for every unreleased pair; evaluation
  hard checks.
- **Deployment:** `argus-actor` on vm-095; an action gateway + socket proxy per host, deployed only when a pair is
  released; firewall rule from the actor only; per-host tokens with rotation.
- **Brain:** `policies/SECURITY.md` "Read-only" principle → "Supervised writes"; `PARALLEL_LANES.md` (actions need
  the host's lease; leases are holds); `AGENT_PROTOCOL.md` (the agent never answers approvals or edits the write
  gate); `REVIEW_PROTOCOL.md` + `brain.py` `SELF_MERGE_PROTECTED` (the new safety paths); `RUNBOOK-CONVENTIONS.md`
  (the Actions section).
- **Risk:** a wrong but approved action on a lab container; mitigated by runbook menus, `never` rules, identity
  binding, precheck, lab-only scope, rate limits, the emergency stop, verification.
- **How to reverse it:** empty `write_gate.open`, stop the action gateways, close their firewall rules (one rehearsed
  `code.bash` block); the read-only diagnosis is unaffected.
- **Safety principles touched:** yes: read-only, write gate, least privilege, secrets. Second approval required.

## 5. Decision

Proposed. To be accepted or changed in the NEXT-PHASE proposal PR review. Implementation starts only after ACR-0018
is applied and deployed; the first release of a pair is its own reviewed PR.

## 6. Applied

- [ ] `ARCHITECTURE.md` updated (§1.2, §1.4, §4.5, §12.2, §13.3, §14.3, §14.4, §14.8, §15.1, §17.2, §21.2, §22,
      changelog), version bumped
- [ ] `policies/SECURITY.md`, `PARALLEL_LANES.md`, `AGENT_PROTOCOL.md`, `REVIEW_PROTOCOL.md`, `RUNBOOK-CONVENTIONS.md`
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
