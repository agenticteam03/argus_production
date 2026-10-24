# ACR-0019 — Human-approved remediation: actions from service and action cards, a human approves, the worker executes

Part of the next-phase proposal ([task](../../tasks/current/NEXT-PHASE-supervised-remediation.md)). Depends on
[ACR-0018](ACR-0018-operator-access-and-audit.md) (operator access and audit), which must be applied and deployed
before phase 19 and any write-gate release; phases 17 and 18 may start earlier under this ACR's §5. Revised 2026-10-18
to merge `conantkd`'s proposal "Argus actúa" (the catalogue, service and action cards, risk
colours, prediction, memory, judge, scenarios with answer keys) with this one.

| Field | Value |
|---|---|
| Status | `accepted` with the approvals of `task/ACR-0019-accepted` (§5); it merges only with them. Not applied: that is phases 17 to 20 |
| Proposed by | juanbetancurm and conantkd (+ agents) · 2026-10-18 |
| Accepted by | a teammate approving `task/ACR-0019-accepted` (proposed there by `conantkd` · 2026-10-23) |
| Second approval (safety principle only) | **required**: read-only and the write gate (the first released write capability), least privilege (a new gateway), secrets (action-gateway tokens). Given by the approvals required to merge `task/ACR-0019-accepted` (AGENT_PROTOCOL §4: any team member's approval counts, the author's included, and one person may give both) |
| Architecture version | the next free version when applied (after ACR-0018) |
| Task / PR | NEXT-PHASE · PR #170 (proposed) · `task/ACR-0019-accepted` (accepted; open decisions 4, 6, 8 and 9 answered, 5 and 10 set per phase) |

## 1. Detect and explain

Argus diagnoses and recommends; a human then repairs by hand, outside Argus, with no link back to the incident. The
team wants the next step: Argus **proposes a fix from a closed catalogue**, an authenticated **human approves** that
exact proposal, the worker executes it through an exact-route gateway, and Prometheus confirms the recovery.

ARCHITECTURE designs most of the path (§4.5 action gateway, §13.3 write gate, §14 approval → resume → precheck →
ledger → reconcile → verify, §14.8 the write contract, §22.2 release criteria), but:
- **none of it is implemented** (OP-015): no `action_proposal` / `approval` / `action` / `target_hold` tables, no
  write contract, no approval routes; `argus/policy/engine.py` refuses to start with a non-empty `write_gate.open`,
  and `tests/test_write_gate_standing.py` requires that no write capability is registered;
- a proposal is not tied to **who may touch what** (a service's owner, its criticality, which actions it allows) nor
  to **why the action should work** (a runbook, a verified earlier fix, the vendor's documentation);
- nothing predicts what a fix should change, or remembers whether a fix worked.

## 2. Why the current architecture is insufficient

Human approval protects the *decision*, not its inputs or its execution. Live gauges show symptoms, not causes or
targets. Cases the current design does not close:

1. **The data supports the wrong action:** in SC-03 the victim (`argus-lab-api`) looks broken on every graph.
2. **Same name, two hosts:** `argus-lab-worker` exists on vm-095 and vm-166.
3. **Approval and execution happen at different times:** the target can be recreated, the incident resolved, a
   teammate's scenario started in between.
4. **What runs can differ from what was shown** if the dispatch path reads anything the model or a log can influence
   (a log line escaped its data block before #166).
5. **"Live" data has gaps:** cached views, stale metrics, `unknown` links.
6. **Approval fatigue, partial failures and our own bugs.**
7. **No source of authority:** §1.3 says the runbooks' mutating actions are candidates, but a runbook does not say
   whether *this* service may be touched; RB-003 requires "a separately authorized target" for a dependency.

## 3. Smallest reasonable change

### 3.1 Responsibility (new paragraph in §1.4, after rule 9)

> The approving operator is accountable for the decision to execute a specific, frozen proposal. The team is
> accountable for which actions Argus may propose (the catalogue, the service and action cards, the risk table, all
> reviewed in pull requests), for the accuracy and completeness of what the approver is shown, and for ensuring that
> only the approved action runs, on the approved target, at most once, with its outcome verified and recorded. Human
> approval is required but never sufficient: every action also passes the controls of §13–§14.

Rule 2 is **unchanged**: every write needs the explicit approval of an authenticated human, given at the time. There
are no pre-approvals in this release (§3.10).

### 3.2 §1.2

Before: "In this release **no write capability is released**: Argus is read-only, and remediation is performed by
humans." After: "Write capabilities are released per `(capability, scope)` (§13.3, §22.2), on lab targets only in this
release. Each execution needs an authenticated human's approval of a frozen proposal (§14). Argus never writes a
command: it picks an action and its parameters from closed lists."

### 3.3 The catalogue (§12.2)

- A closed catalogue of **typed actions**, organized by intent: start, stop/contain, limit resources, reload, roll
  back, free disk, fix configuration.
- Each action has a canonical name (`container.start`) and a model name (`start_container`), like the reads.
- **The model never writes commands.** It picks a capability and its parameters from enums; the gateway translates
  the call into one exact API route. A made-up action has nothing that could execute it (`fabricated_tool`, a
  security event).
- **First catalogue, Docker (`action-gateway`):**
  - `container.start`, `container.restart`, `container.stop`, `container.pause`, `container.unpause`;
  - `container.update_resources`, `container.signal`;
  - `container.network_connect`, `container.network_disconnect`;
  - `deployment.rollback`, `docker.prune_images`, `docker.prune_build_cache`.

  Later families (PostgreSQL `db-action`, configuration with a hash lock, Linux `host-action`, generated tools) each
  come with their own ACR.
- **Never offered** (no enum value, no gateway route, a standing test):
  - restarting the victim instead of the cause (RB-002, RB-003);
  - the Docker or containerd daemon (RB-017);
  - deleting data, WAL or volumes;
  - flushing firewall or DNS rules; lowering TLS security; moving the clock back;
  - Argus itself (`argus-v18-*`), Prometheus, Alertmanager, the gateways and the probes;
  - `exec`, `archive`, privileged containers, mounting the Docker socket;
  - free SQL;
  - installing packages, creating users, kernel changes.
- **`suggest_action(text, closest_capability?)`:** a new decision for when no catalogue action fits or no source
  supports one. It is text for the operator and never executes; the suggestions are the backlog of actions to add.

### 3.4 Service cards and action cards (§5.8, §13.1)

**Service card**: a `service:` block per target in `config/inventory.yaml`, written by the service's owner and
reviewed in a PR. It is part of `inventory_version`, so a change between approval and execution cancels at precheck.
Fields:
- `role`, `kind` (`stateless` | `stateful` | `proxy` | `database`), `owner`, `criticality` (`low` | `medium` |
  `high`), `data` (`ephemeral` | `persistent`);
- `safe_actions` (each with parameter bounds), `never` (e.g. `container.restart` on the database);
- `allowed_networks`, `verify`, `quirks`.

It is the "separately authorized target" RB-003 asks for.

**Action card**: one file per action in `config/actions/`, reviewed in a PR. Fields:
- the executor, the exact route, the parameters, and the identity fields;
- `preconditions` as expressions over fresh observations, evaluated by a minimal interpreter (comparisons, `in`,
  `and`, `or`; **never `eval`**);
- `useful_when` and `not_useful_when` (e.g. "it died of OOM: a restart will not help, the action is
  `update_resources`");
- `verify` (signals and window), `rollback`;
- `risk` per target kind;
- `sources` (runbook ids, reference ids).

### 3.5 Grounds and basis: when Argus may propose (§11.2, §11.3)

A proposal answers three questions, each from a source that is cited and stored as evidence:

| Question | Source | Required |
|---|---|---|
| What is happening? | the incident's evidence | always |
| May this be touched here? | the **service card** (`safe_actions`), or a runbook that names the action | always |
| Why will this action fix it? | a runbook's `actions` block, the **memory of verified actions**, or curated vendor documentation | always |

- The **basis** (`runbook` | `memory` | `reference` | `operator`) is computed by code from the cited grounds; the
  model never declares it.
- A proposal whose only basis is the model's own knowledge, or that cites an internet result, is **downgraded to a
  suggestion** (`decision.downgraded_to_suggestion`).
- A manual action by the operator (ACR-0020) or a suggestion the operator turns into a proposal (basis `operator`)
  follows the same rule: allowed only when the service card and the action card permit it, with cited evidence.

### 3.6 The mandatory shape of a proposal (§5.6, §11.2)

`ProposeRemediation` carries:
- `capability`, `target` and `arguments` (enums; validated against the action card and the service card's bounds);
- `root_cause`, and a `rationale` that says why it addresses the cause and not the symptom;
- `evidence_refs` (the current state), `grounds` (why it works);
- a **`prediction`**: the signal on the target that must reach the expected value within N seconds (e.g. the victim's
  `dependency_probe_min == 1` within 120 s);
- 1–3 **`alternatives`**, from the least to the most invasive, each with `why_not`.

A proposal missing any of them is `InvalidDecision(malformed)`. The digest also covers the preview (`dry_run` or
diff, where the action has one) and the rollback plan.

### 3.7 Risk colours (`config/risk.yaml`, §13.1)

- **Colours:**
  - **green**: reversible, no data loss, a stateless target;
  - **amber**: reversible, but it cuts connections or work in progress;
  - **red**: hard to reverse, or a data risk;
  - **forbidden**: never offered.
- **Set by people** in a reviewed table, per action **and** target kind (from the service card): restarting the
  ephemeral cache is green; restarting the database is forbidden. The model never rates risk.
- **The colour of one proposal can only go up:** `criticality: high` raises it one level, a judge's `disagree` raises
  it one more.
- **The approver sees the colour.** A **red** proposal needs the approver to type the target's name to confirm.

### 3.8 The judge (§10, §11)

- A second model call reviews the **frozen** proposal: its extracts of evidence and grounds, the service card and the
  action card, without the deciding model's conversation. It answers a fixed schema: `verdict` (`agree` | `doubt` |
  `disagree`), `checks` (evidence supports the cause, the action addresses the cause, the grounds support the action,
  a less invasive alternative exists, the risk is understated) and `reasons`.
- It **can only make things stricter:** it raises the colour, and shows its reasons to the approver. It never
  approves or changes the proposal.
- Its verdict is stored as evidence. A timeout or invalid answer counts as `doubt` (fail closed). Its agreement with
  human decisions is measured.

### 3.9 Execution by the worker (§4.5, §17.2)

The worker that runs the investigation also dispatches the approved action (as §17.2's "Worker write identity |
`local_write.py`" designs). The controls that keep the model out of the execution path:
- `execute_write` reads **only** the frozen `action_proposal` and `approval` rows from Postgres; it never receives
  model output or context. The module that dispatches cannot import the LLM adapter or the harness (an
  import-boundary test, §2.3).
- The action-gateway token is mounted for the worker process only. The MCP tools child (`argus-tools` UID, ACR-0002)
  cannot read it (the credential-isolation test, now run in CI).
- The gateway accepts only the released `(route, target)` pairs, requires `X-Argus-Action-Id`, keeps a journal, and
  reaches Docker through a **socket proxy** with path ACLs.
- One action per target at a time (the §14.4 lock), no other action on the same target within 10 minutes, a daily cap
  per host.

### 3.10 The human is the final approver (§14.3)

- **The approval view** shows the frozen proposal:
  - capability, host-qualified target and its identity, arguments;
  - colour, basis and grounds, prediction, alternatives;
  - the judge's verdict and reasons;
  - the precheck preview, reversible yes/no, the expiry (proposed 30 min in the lab).
- **Answering** needs the `approve_action` permission, a human principal, the private path and a step-up bound to
  `approval_id + proposal_digest` (ACR-0018). The UI over the private path is the main path; the CLI and Swagger on
  loopback stay.
- **No pre-approvals, veto windows or autonomous execution in this release.** Shadow mode records, for each approved
  green/amber proposal, whether a future autonomy rule *would* have allowed it. This is measurement only, for a later
  ACR.
- **Holds:** an approver can place a hold or pull the emergency stop (a global hold) at once from the UI or the CLI.
  Raising power is a reviewed PR; lowering it is one click.

### 3.11 Precheck (§14.4 step 7), additions

- the action card's preconditions, re-evaluated on fresh reads;
- no hold, including the automatic hold while another developer holds the host's lease;
- the target identity is unchanged;
- the class is still detected;
- the service and action cards are unchanged (`inventory_version`, `policy_version`).

### 3.12 Verification, outcomes and memory (§5.3, §15)

- **Verification:** `verify` waits for a Prometheus sample after the action, runs the class's detector **and checks
  the prediction**. Only `recovered_verified` counts as success; a missed prediction is recorded against the action.
- **New outcomes in `IncidentOutcome`:** `recovered_verified`, `action_failed`, `indeterminate_escalated`, `denied`,
  `expired` (`resolved_externally` and `no_action_escalated` exist).
- **The memory of verified actions:** at `record`, an insert-only `action_outcome` row stores the redacted symptom
  signature, the class and target kind, the action and argument shape, the basis, the result, what the human did
  (approved, denied with a reason, did it manually), and the origin (lab, drill, production).
  `knowledge.prior_incidents` returns it, e.g. "this action ended `recovered_verified` 3 of 3 times on this service".
- **Resolution summary:** the record distinguishes "service recovered" from "cause resolved". When the same symptom,
  action and grounds verify several times, Argus drafts a runbook `actions` block for a human to review and promote.

### 3.13 Release scope and evaluation (§13.3, §21.2, §22)

- `write_gate.open` lists `(capability, scope)` pairs; the only scope in this release is `lab` (`argus-lab-*`).
  The first released pair: `container.start` on `vm-166/container:argus-lab-cache` (SC-03), its own release PR, two
  reviewers.
- **The evaluation grades actions:**
  - each scenario has an answer key with the outcome correct / acceptable / useless / harmful;
  - trap scenarios, where escalating or doing nothing is the right answer;
  - new hard checks at 0: `unauthorized_actions`, `actions_on_forbidden_targets`, `action_without_valid_approval`,
    `harmful_actions`.

**Alternatives considered:**
- A: **a separate executor (`argus-actor`) that never runs the model.** Stronger isolation, but a new container,
  token and claim loop. Rejected for this release in favour of §3.9's controls (the dispatch reads only frozen rows;
  an import-boundary test; the tools child cannot read the token). Reconsider if a review finds a path from model
  output to dispatch.
- B: **actions only from runbook menus.** Safer but too narrow: almost no runbook names an exact action today.
  Replaced by service and action cards with cited grounds, where a runbook is one source.
- C: **earned autonomy** (pre-approvals, veto windows, `actor = grant:…`), as in conantkd's phase 4. Deferred: it
  changes rule 2 and needs shadow-mode data first. Shadow mode starts now (§3.10).
- D: **the model writes the command and the operator approves the text.** Rejected: the text shown and the command
  run can diverge.
- E: **keep Argus read-only.** Safe, but remediation stays manual and unlinked; ACR-0020 covers manual repair.

## 4. Consequences

- **Domain:** `ProposeRemediation`, `SuggestAction`, `Prediction`, `Alternative`, `ActionProposal`, `Approval`,
  `ActionRecord`, `ActionOutcome`; the new `IncidentOutcome` values.
- **Policy:** the write gate per scope, holds, approvers, the action-card interpreter, `config/risk.yaml`, the service
  cards.
- **Orchestration:** nodes `propose_action`, `judge_proposal`, `request_approval`, `await_approval` (LangGraph
  `interrupt`), `precheck_action`, `execute_write`, `verify`; harness conversion rules for proposals and suggestions.
- **Store:** migration with §14.1's tables, `action_outcome`, `judge_verdict` evidence.
- **Gateway:** the action gateway + socket proxy on each host, deployed only when a pair is released.
- **API/UI:** approvals, holds, the emergency stop, suggestions, the incident's Actions tab (ACR-0018 for access).
- **Tests before any release:**
  - the §14.4 failure-injection suite;
  - the §22.2 binding tests;
  - the action-card interpreter (no `eval`; malformed expressions refused);
  - "colour only goes up";
  - judge fail-closed;
  - a model-only basis is downgraded;
  - an internet ground is refused;
  - the import boundary of the dispatch module, and the tools child cannot read the action token;
  - gateway exact routes and socket proxy on real images;
  - reconciliation and `indeterminate` → escalate;
  - the standing write-gate test for every unreleased pair;
  - the scenario answer keys.
- **Brain:**
  - `policies/SECURITY.md`: "Read-only" becomes "Supervised writes";
  - `PARALLEL_LANES.md`: actions need the host's lease, and leases are holds;
  - `AGENT_PROTOCOL.md`: the agent never answers approvals or edits the write gate;
  - `REVIEW_PROTOCOL.md` + `SELF_MERGE_PROTECTED`: `config/actions/`, `config/risk.yaml`, the dispatch module, the
    gateway;
  - `RUNBOOK-CONVENTIONS.md`: the runbook `actions` block.
- **Risk:** a wrong but approved action on a lab container. Mitigated by:
  - the closed catalogue and the cards;
  - colours and the judge;
  - the prediction, identity binding and precheck;
  - lab-only scope, rate limits, holds and the emergency stop;
  - verification.
- **How to reverse it:** empty `write_gate.open`, stop the action gateways, close their firewall rules (one rehearsed
  `code.bash` block); diagnosis is unaffected.
- **Safety principles touched:** yes (read-only, write gate, least privilege, secrets). Second approval required.

## 5. Decision

Proposed in #170 by juanbetancurm and conantkd, merging both proposals. **Accepted** with the approvals of
`task/ACR-0019-accepted`: one teammate's, plus the second one for the safety principles touched (read-only and the
write gate, least privilege, secrets). §3 is accepted as written. Acceptance changes no code and no `ARCHITECTURE.md`
text: this ACR is applied phase by phase, each with its first code (§6). The first release of a pair is its own
reviewed PR with two reviewers (§3.13).

The answers below are to the NEXT-PHASE open decisions that belong to this ACR (4, 5, 6, 8, 9 and 10); decision 1
belongs to ACR-0020.

1. **First released pair (decision 4):** `container.start` on `vm-166/container:argus-lab-cache`, scope `lab`. The
   cache is stopped in SC-03, so `start` is the narrower action; `container.restart` is not released in the first
   release.
2. **The judge's model (decision 5): not decided here.** It is chosen when phase 18 starts, from a small measured
   comparison on good, bad and trap proposals, and recorded in that phase's journal. The constraint of §3.8 stands
   (a model other than the deciding one; its cost recorded). The starting proposal is a smaller model of the provider
   already in use; a second provider is a later change with its own evaluation.
3. **Approval expiry and rate (decision 6):** 30 minutes in the lab; one action per target at a time and none on the
   same target within 10 minutes (§3.9); the daily cap per host is set in the release PR.
4. **Actions on vm-095 (decision 8):** none. It is Argus's own host; no pair is released there.
5. **Drills as memory (decision 9):** the memory of verified actions is counted per origin (lab, drill, production);
   lab and drill counts never apply to production.
6. **Evaluation budget (decision 10): not fixed here.** Each of phases 17, 18 and 20 states its budget in its plan
   before running a batch. A reference measured on #301: one 60-run arm of a model batch used about 1.1 million
   input tokens and 90 thousand output tokens.

**Sequencing.** Implementation follows ACR-0018. This acceptance proposes one clarification to that precondition:
phases 17 and 18 release no write capability and add no approval route (cards, suggestions, the §14 machinery against
a fake gateway, with `write_gate.open` empty and the standing write-gate test unchanged), so they may start once this
ACR is accepted. Phase 19 (approvals in the UI, the gateway) and any `write_gate.open` entry need ACR-0018 applied and
deployed in full: the off-host audit digest (phase 16 step 5) and the phase 16 exit proof (step 6). No approval is
accepted on an audit trail that someone with `sudo` on the VMs could rewrite.

## 6. Applied

- [ ] `ARCHITECTURE.md` updated (§1.2, §1.4, §4.5, §5.3, §5.6, §5.8, §10, §11.2, §11.3, §12.2, §13.1, §13.3, §14.3,
      §14.4, §15, §17.2, §21.2, §22, changelog), version bumped
- [ ] `policies/SECURITY.md`, `PARALLEL_LANES.md`, `AGENT_PROTOCOL.md`, `REVIEW_PROTOCOL.md`, `RUNBOOK-CONVENTIONS.md`
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
