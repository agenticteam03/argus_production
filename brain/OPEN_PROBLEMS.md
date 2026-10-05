# Open problems and pending team decisions

When a problem is fixed, set its status to `fixed` with the date, and add a journal entry if it is significant.
**Status:** `open` · `in progress` · `fixed` · `dropped` (with reason) · decisions: `pending` · `decided`

| ID | Item | Status | Opened |
|---|---|---|---|
| **D-001** | Cross-host path and alert direction: architecture text vs the running system | **pending team decision** | 2026-10-02 |
| **D-002** | Move the runbook library into this repository (the architecture expects it there) | **decided and done** 2026-10-02 | 2026-10-02 |
| OP-001 | Runbook `detector` metadata uses old or empty class names | open | 2026-09-30 |
| OP-002 | P0 safety gaps of the runbook library not yet reconciled with architecture v1.8 | open | 2026-09-30 |
| OP-003 | Runbook safety classes not mapped to `CapabilitySpec.risk` | open | 2026-09-30 |
| OP-004 | LangGraph checkpoints grow forever; checkpoints of failed runs are orphaned | accepted 2026-10-05 — to implement | 2026-10-05 |
| OP-006 | LangGraph `recursion_limit` is fixed at 100 and can be too small for larger step budgets | open | 2026-10-05 |

---

## D-001 — Cross-host path and alert direction (pending team decision)

**Status:** pending · **Opened:** 2026-10-02 · **Decided by:** the whole team (including `conantkd`)

**The difference.** Architecture §3.6 (reference values) says the two hosts talk over the **private network with no
tunnel**, and that alerts are **pushed** (Alertmanager on vm-166 → webhook on vm-095). The running system uses a
**restricted SSH tunnel** over port 22 (the only port open between the VMs) and **pulls** alerts through it
(`ReconcileFiringAlerts`), because the cloud network rules cannot be changed by the team.

**Options.**
- **A. Keep the architecture text; change the deployment later.** If someone with access to the cloud console opens
  the needed ports between the private addresses, switch to the private network and push alerts. Only the inventory
  URLs, the compose port bindings and the alert route change; the tunnel is removed.
- **B. Change the architecture to match the running system** through an ACR (§3.6: SSH tunnel, pulled alerts).
- **C. Use the existing WireGuard tunnel** — only with `conantkd`'s agreement, since it belongs to the protected
  deployment.

**Until decided:** the running system stays as it is (tunnel + pull). Nobody changes the architecture text or the
transport alone.

**Done when.** The team has chosen; the result is either an accepted ACR (B) or a planned task (A or C), recorded in
the journal.

---

## D-002 — Move the runbook library into this repository

**Status:** decided and done (2026-10-02, owner: deploy keys are disabled in the organization, so CI could not read
the separate repository; moving the library removes the need) · **Opened:** 2026-10-02

**The difference.** Architecture §2.4 places the runbooks in the code repository (`argus/runbooks/`, "reviewed copy
of the runbook library v1.1.0" + `RUNBOOK-CONVENTIONS.md`). The running system reads them from a separate private
repository (`agenticteam03/runbooks`, pinned in `config/runbooks.lock`). That came from an implementation choice on
2026-09-30 ("read in place, never copied") and the shared-Brain plan decision D2, not from the architecture. It costs
a deploy key for CI, a deploy key per VM, and a pin bump plus a second repository for every runbook change.

**Done.** Moved (without history: the old repository keeps it; provenance in `argus/runbooks/README.md`) the reviewed runbooks (RB-001…RB-021, `RUNBOOK-CONVENTIONS.md`, `RUNBOOK-INDEX.md`) into
`argus/runbooks/` with their history (`git subtree`), keep each runbook's own `version` in its metadata (already
recorded in the recall audit), deploy them with the code, retire `config/runbooks.lock` and the CI deploy key, and
leave the research material (books, assessments, gap backlog) in the old repository as history. OP-001 is then fixed
in this repository.

**Alternative.** Keep the separate repository (works today; costs as above).

**Done when.** Decided; if yes, done as one task (tests: recall finds every class's runbooks from `argus/runbooks/`;
deployment no longer mounts `/opt/argus-runbooks`) and the journal records it.

---

## OP-001 — Runbook `detector` metadata uses old or empty class names

**Status:** open · **Opened:** 2026-09-30

**Problem.** Each runbook in the library (`agenticteam03/runbooks`, `runbooks/RB-*.md`) has a `detector:` field. It
still uses v1.7 names or is empty: RB-001 `oom_restart_loop` (v1.8: `container_restart_loop`, shared with RB-008);
RB-002 `health_check_failed` and RB-003 `dependency_unavailable` already match; RB-004…RB-021 `null`. Architecture
§15.3 requires that "a runbook's `detector` metadata names the class that uses it".

**Fix.** In the runbooks repository: set `detector:` in every runbook to its v1.8 class (§1.3); bump `version` and
`last_reviewed`; update `RUNBOOK-INDEX.md`. Now done in this repository (`argus/runbooks/`), through a pull request.

**Done when.** All 21 runbooks name a class that exists in §1.3, and a check shows no class without a runbook and no
runbook without a class.

---

## OP-002 — P0 safety gaps not yet reconciled with architecture v1.8

**Status:** open · **Opened:** 2026-09-30

**Problem.** The library's `ARGUS-CAPABILITY-GAPS.md` lists eight **P0** gaps written against an older code base.
Each must be settled in the architecture (ACR) before the related implementation. First assessment — to be verified:

| Gap | Asks for | Against v1.8 | Likely change |
|---|---|---|---|
| G-001 Deployment profiles | named, versioned profiles (production / lab); missing profile fails closed | partial: per-(capability, target) write gate, no profile | `profile` in the policy file; write gate evaluated per profile |
| G-002 Typed prerequisites | preconditions as typed predicates on fresh, identity-bound evidence | **missing**: §13.1 uses free-text `preconditions` | typed predicates evaluated at `propose_action` and `precheck_action` |
| G-003 Observation provenance | source vs collection time, coverage, units, partial state, identities | partial | add the fields to `Observation` / `EvidenceRecord`; missing is never zero or healthy |
| G-004 Approval binding | immutable proposal bound to what it acts on, previews | mostly covered | extend `identity()`; preview in the approval view |
| G-005 Verification windows | stability windows, provisional vs final recovery | partial | `stability_window` per class; provisional/final states |
| G-006 Data minimization | per-source field allowlists, literal redaction | partial | `allowed_fields` per `CapabilitySpec` |
| G-007 Helper semantics | missing/partial data never becomes healthy or root cause | principle missing (implemented for metrics freshness) | state the rule in §12.3; contract fixtures |
| G-008 Corpus/dispatcher separation | runbook IDs from metadata, bounded passages, tools never from runbook text | covered by §15.3 | verify that writes are offered only for registered classes |

**Done when.** Each gap is covered, changed through an ACR, or dropped with a reason.

---

## OP-003 — Runbook safety classes not mapped to `CapabilitySpec.risk`

**Status:** open · **Opened:** 2026-09-30

**Problem.** The library's conventions classify operations as `READ_ONLY_SAFE`, `READ_ONLY_SENSITIVE`,
`MUTATING_LOW_RISK`, `MUTATING_HIGH_RISK`, `FORBIDDEN`; architecture §12.3 uses `risk: low | medium | high | very_high`
plus `permission: read | write_hitl`. They do not map cleanly (sensitive reads need allowlists; `FORBIDDEN` has no
equivalent).

**Fix (to discuss, ACR).** Adopt the five classes as `safety_class`, derive `permission` from it; sensitive reads get
mandatory field allowlists (ties to G-006); `FORBIDDEN` operations are never registered; classify every capability in §12.2.

**Done when.** §12.3 has one scheme; every capability has a class; policy and redaction rules refer to it.

---

## OP-004 — Checkpoint retention (accepted, to implement)

**Status:** accepted 2026-10-05 (PR #7, approved by `conantkd`) · **Opened:** 2026-10-05 · **Found by:** `conantkd` (T-0013 review)

**Problem.** Since T-0013 every investigation leaves rows in `checkpoints`, `checkpoint_blobs` and `checkpoint_writes`,
and nothing ever removes them: the runtime role has no DELETE (on purpose, migration 002). A run that ends with an
exception leaves a pending checkpoint that is never resumed, because its incident is already final. Small today, but
it grows without limit.

**Proposed solution — an automatic cleanup policy:**
- a small script `ops/checkpoint-retention.sh` on vm-095, run **as the owner role** inside the Postgres container
  (the runtime role keeps "no DELETE anywhere"), once a day by a systemd timer (later by the Argus scheduler);
- it deletes the checkpoint rows (all three tables) of threads whose incident is final (`closed` or `escalated`) and
  ended more than **30 days** ago (configurable: `ARGUS_CHECKPOINT_RETENTION_DAYS`); a final incident's checkpoints
  are never needed again, because a final incident is never resumed;
- the same rule removes the orphaned checkpoints of failed runs (their incident is final too);
- it never touches incidents, evidence, audit or run events (they stay insert-only), and it records each run as an
  audit row `maintenance.checkpoints_pruned` with the number of threads removed;
- `argus db check` keeps proving that the runtime role cannot delete checkpoints.

**Alternatives.** Keep everything (disk grows; fine for months at today's volume) · delete at the end of every run
(loses the record of how a run progressed, and needs DELETE for the runtime role — rejected).

**Done when.** Approved here; then a task implements the script, its Postgres test (old final threads removed, recent
and non-final ones kept, evidence and audit untouched) and the timer on vm-095, with NO INTERFERENCE.

**Review conditions (conantkd, PR #7) — part of the accepted proposal:**
1. Implement it as an Argus command (for example `argus db prune-checkpoints`) run with the owner DSN, not as a
   standalone SQL/bash script: the audit row is then written by the same code and in the same format as every other
   audit row, and the Postgres tests can cover it. The systemd timer (named `argus-v18-*`) only calls that command.
2. Dry-run first: the command reports what it would delete without deleting; the first runs on vm-095 are dry-runs.
   Deleting database rows is a stop condition (`agents/AGENT_PROTOCOL.md` §6) and the Postgres backup/restore drill
   is not done yet.
3. The `incident` table has no end-time column: "ended" means `body->>'closed_at'` (set when the incident becomes
   final); an incident without it is never pruned.

---

## OP-006 — LangGraph `recursion_limit` is fixed at 100 and can be too small for larger step budgets

**Status:** open · **Opened:** 2026-10-05 (T-0013 review, conantkd)

**Problem.** `GraphRunner.run` passes `recursion_limit: 100` to LangGraph (`argus/orchestration/graph_runner.py`).
Since the T-0013 review fix, `act` and `evidence_pack` make one read per graph step, so one investigation round costs
`1 + reads` graph steps instead of 2. The worst case is `max_steps × (1 + max(ARGUS_MAX_READS_PER_STEP, 6)) + 4`
(6 = the largest deterministic plan, the evidence pack, which the model's read limit does not cap). With the defaults
(8 steps) it is 60, below 100. With `ARGUS_MAX_STEPS=20` it is 144: the run would stop with `GraphRecursionError`
although Argus is still inside its own budget.

The round budget is not chosen by the model: `recall` sets it to `min(class max_steps, ARGUS_MAX_STEPS)` and
`investigate` only counts it. An infinite loop is still impossible as long as the limit is a fixed number.

**Fix (agreed in review).** `recursion_limit = max(100, max_steps_cap × (1 + max(max_reads_per_step, largest plan)) + 4 + 10)`:
unchanged (100) with today's configuration, grows only when the budgets need it. Tests: the default limit is 100; with
20 steps × 5 reads a model that exhausts the budget ends `escalated`, not with `GraphRecursionError` (red first).
Separate, optional: refuse to start when `ARGUS_MAX_STEPS` is above a sane ceiling (for example 30), so a typo cannot
create a huge budget (cost of model calls and reads).

**Done when.** The limit is derived from the budgets, both tests pass, and this item is set to `fixed`.
